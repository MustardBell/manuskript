"""Explicit, revision-aware RPC projection of portable plugin capabilities."""

import hashlib
import json
import threading
import uuid

from dataclasses import dataclass, fields, is_dataclass

from manuskript.plugins.capabilities import (
    CAPABILITY_ASSERTIONS_READ,
    CAPABILITY_CONVERSION,
    CAPABILITY_ENTITIES_READ,
    CAPABILITY_ENTITIES_WRITE,
    CAPABILITY_MORPHOLOGY_SCHEMAS,
    CAPABILITY_PROSE_ANALYSIS,
    CAPABILITY_REFERENCES_READ,
    CAPABILITY_RULES_EXECUTE,
    CAPABILITY_TIMELINE_READ,
    CAPABILITY_WORKFLOW_READ,
    CAPABILITY_WORKFLOW_WRITE,
)
from manuskript.plugins.errors import (
    PluginConflictError,
    PluginProtocolError,
    PluginScopeError,
)
from manuskript.plugins.values import api_value_codec


@dataclass(frozen=True)
class CapabilityMethod:
    capability: str
    name: str
    positional: tuple = ()
    optional: tuple = ()
    keyword: tuple = ()
    mutates: bool = False
    revision_reader: str = ""

    @property
    def schema(self):
        return {
            "name": self.name,
            "positional": self.positional,
            "optional": self.optional,
            "keyword": self.keyword,
            "returns": "api_value",
            "mutates": self.mutates,
            "revision": (
                "required" if self.revision_reader else "not_accepted"
            ),
        }


CAPABILITY_METHODS = (
    CapabilityMethod(CAPABILITY_CONVERSION, "routes"),
    CapabilityMethod(
        CAPABILITY_CONVERSION,
        "can_convert",
        ("source_format", "target_format"),
    ),
    CapabilityMethod(
        CAPABILITY_CONVERSION,
        "convert",
        ("text", "source_format", "target_format"),
        ("page_type",),
    ),
    CapabilityMethod(CAPABILITY_ENTITIES_READ, "entities"),
    CapabilityMethod(CAPABILITY_ENTITIES_READ, "find", ("entity_id",)),
    CapabilityMethod(
        CAPABILITY_ENTITIES_READ, "exact_matches", ("surface",)
    ),
    CapabilityMethod(CAPABILITY_ENTITIES_WRITE, "entities"),
    CapabilityMethod(CAPABILITY_ENTITIES_WRITE, "find", ("entity_id",)),
    CapabilityMethod(
        CAPABILITY_ENTITIES_WRITE, "exact_matches", ("surface",)
    ),
    CapabilityMethod(
        CAPABILITY_ENTITIES_WRITE,
        "create",
        ("entity_type", "title"),
        ("aliases",),
        mutates=True,
    ),
    CapabilityMethod(
        CAPABILITY_ENTITIES_WRITE,
        "update",
        ("entity_id",),
        keyword=("title", "entity_type", "aliases", "text"),
        mutates=True,
        revision_reader="find",
    ),
    CapabilityMethod(CAPABILITY_REFERENCES_READ, "occurrences"),
    CapabilityMethod(
        CAPABILITY_REFERENCES_READ, "backlinks", ("target_id",)
    ),
    CapabilityMethod(CAPABILITY_REFERENCES_READ, "complete", ("prefix",)),
    CapabilityMethod(CAPABILITY_ASSERTIONS_READ, "assertions"),
    CapabilityMethod(
        CAPABILITY_ASSERTIONS_READ, "find", ("assertion_id",)
    ),
    CapabilityMethod(
        CAPABILITY_ASSERTIONS_READ,
        "relationships",
        optional=("predicate",),
    ),
    CapabilityMethod(CAPABILITY_ASSERTIONS_READ, "diagnostics"),
    CapabilityMethod(CAPABILITY_TIMELINE_READ, "chronology"),
    CapabilityMethod(CAPABILITY_TIMELINE_READ, "diagnostics"),
    CapabilityMethod(
        CAPABILITY_TIMELINE_READ, "compare", ("left", "right")
    ),
    CapabilityMethod(
        CAPABILITY_TIMELINE_READ,
        "facts",
        ("at",),
        keyword=("subject", "predicate", "include_unknown"),
    ),
    CapabilityMethod(CAPABILITY_RULES_EXECUTE, "rules"),
    CapabilityMethod(CAPABILITY_RULES_EXECUTE, "diagnostics"),
    CapabilityMethod(
        CAPABILITY_RULES_EXECUTE, "execute", optional=("rule_ids",)
    ),
    CapabilityMethod(
        CAPABILITY_PROSE_ANALYSIS,
        "analyze",
        keyword=(
            "ngram_min",
            "ngram_max",
            "minimum_repetitions",
            "opening_words",
            "nearby_distance",
            "fillers",
            "maximum_results",
        ),
    ),
    CapabilityMethod(CAPABILITY_WORKFLOW_READ, "passes"),
    CapabilityMethod(CAPABILITY_WORKFLOW_READ, "documents"),
    CapabilityMethod(CAPABILITY_WORKFLOW_WRITE, "passes"),
    CapabilityMethod(CAPABILITY_WORKFLOW_WRITE, "documents"),
    CapabilityMethod(
        CAPABILITY_WORKFLOW_WRITE,
        "set_state",
        ("document_id", "pass_id", "state"),
        mutates=True,
        revision_reader="documents",
    ),
    CapabilityMethod(CAPABILITY_MORPHOLOGY_SCHEMAS, "schemas"),
    CapabilityMethod(
        CAPABILITY_MORPHOLOGY_SCHEMAS,
        "register_xml",
        ("source",),
        mutates=True,
    ),
)


METHODS_BY_KEY = {
    (method.capability, method.name): method
    for method in CAPABILITY_METHODS
}

EVENT_TOPICS = frozenset((
    "project.changed",
    "structure.changed",
    "selection.changed",
    "document.changed",
))
MAX_SUBSCRIPTIONS = 128


def portable_capability_methods(capabilities):
    """Public RPC method names for each granted capability."""

    names = frozenset(capabilities)
    return {
        capability: tuple(
            method.schema for method in CAPABILITY_METHODS
            if method.capability == capability
        )
        for capability in sorted(names)
    }


class CapabilityRpcRouter:
    """Dispatch only catalogue methods granted to one plugin."""

    def __init__(
        self,
        plugin_id,
        declared_capabilities,
        capability_resolver,
        generation_source,
    ):
        self.plugin_id = str(plugin_id)
        self.declaredCapabilities = frozenset(declared_capabilities)
        self.capabilityResolver = capability_resolver
        self.generationSource = generation_source
        self.codec = api_value_codec()
        self._subscriptions = {}
        self._subscriptionLock = threading.Lock()

    def handle(self, method, params):
        if method == "events/subscribe":
            return self._subscribe(params)
        if method == "events/unsubscribe":
            return self._unsubscribe(params)
        if method != "capability/call":
            raise PluginScopeError(
                "Host method {!r} is not available to plugins."
                .format(method)
            )
        if not isinstance(params, dict):
            raise PluginProtocolError(
                "Capability call params must be an object."
            )
        expected = {
            "capability",
            "operation",
            "arguments",
            "keyword_arguments",
            "project_generation",
            "expected_revision",
        }
        if set(params) != expected:
            raise PluginProtocolError(
                "Capability call fields must be exactly: {}."
                .format(", ".join(sorted(expected)))
            )
        capability = params["capability"]
        operation = params["operation"]
        if not isinstance(capability, str) or not isinstance(operation, str):
            raise PluginProtocolError(
                "Capability and operation names must be strings."
            )
        if capability not in self.declaredCapabilities:
            raise PluginScopeError(
                "Plugin {} did not declare capability {!r}."
                .format(self.plugin_id, capability)
            )
        specification = METHODS_BY_KEY.get((capability, operation))
        if specification is None:
            raise PluginScopeError(
                "Capability {!r} does not publish operation {!r} over RPC."
                .format(capability, operation)
            )
        generation = self._generation()
        requested_generation = params["project_generation"]
        if (
            isinstance(requested_generation, bool)
            or not isinstance(requested_generation, int)
            or requested_generation != generation
        ):
            raise PluginConflictError(
                "Plugin request targets a stale project generation.",
                {
                    "expected_generation": generation,
                    "actual_generation": requested_generation,
                },
            )
        arguments = self.codec.decode(params["arguments"])
        keyword_arguments = self.codec.decode(params["keyword_arguments"])
        if not isinstance(arguments, tuple) or not isinstance(
            keyword_arguments, dict
        ):
            raise PluginProtocolError(
                "Capability arguments must decode to a tuple and map."
            )
        self._validate_arguments(
            specification, arguments, keyword_arguments
        )
        service = self.capabilityResolver(capability)
        operation_method = getattr(service, operation, None)
        if not callable(operation_method):
            raise PluginScopeError(
                "The current project cannot perform {}.{}."
                .format(capability, operation)
            )
        if specification.revision_reader:
            current = self._current_revision(
                service,
                specification,
                arguments,
            )
            expected_revision = params["expected_revision"]
            if expected_revision != current:
                raise PluginConflictError(
                    "Plugin write targets a stale resource revision.",
                    {
                        "expected_revision": current,
                        "actual_revision": expected_revision,
                    },
                )
        elif params["expected_revision"] is not None:
            raise PluginProtocolError(
                "This capability operation does not accept a revision."
            )
        result = operation_method(*arguments, **keyword_arguments)
        return {
            "value": self.codec.encode(result),
            "project_generation": generation,
            "revisions": self._revisions(result),
        }

    def invalidate_subscriptions(self):
        """Discard event routes tied to the prior project generation."""

        with self._subscriptionLock:
            self._subscriptions.clear()

    def event_notifications(self, topic, payload):
        """Create ordered notifications for subscriptions to ``topic``."""

        if topic not in EVENT_TOPICS:
            raise ValueError("Unknown plugin event topic {!r}.".format(topic))
        encoded = self.codec.encode(payload)
        generation = self._generation()
        notifications = []
        with self._subscriptionLock:
            for subscription_id, state in self._subscriptions.items():
                if topic not in state["topics"]:
                    continue
                state["sequence"] += 1
                notifications.append({
                    "subscription_id": subscription_id,
                    "sequence": state["sequence"],
                    "topic": topic,
                    "project_generation": generation,
                    "payload": encoded,
                })
        return tuple(notifications)

    def _subscribe(self, params):
        if not isinstance(params, dict) or set(params) != {
            "topics", "project_generation"
        }:
            raise PluginProtocolError(
                "Event subscription requires topics and project_generation."
            )
        topics = params["topics"]
        if (
            not isinstance(topics, list)
            or not topics
            or any(not isinstance(topic, str) for topic in topics)
            or len(topics) != len(set(topics))
        ):
            raise PluginProtocolError(
                "Event topics must be a nonempty array of unique strings."
            )
        unknown = set(topics) - EVENT_TOPICS
        if unknown:
            raise PluginScopeError(
                "Unknown plugin event topics: {}."
                .format(", ".join(sorted(unknown)))
            )
        self._require_generation(params["project_generation"])
        with self._subscriptionLock:
            if len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
                raise PluginScopeError(
                    "Plugin {} exceeds {} event subscriptions."
                    .format(self.plugin_id, MAX_SUBSCRIPTIONS)
                )
            subscription_id = str(uuid.uuid4())
            self._subscriptions[subscription_id] = {
                "topics": frozenset(topics),
                "sequence": 0,
            }
        return {
            "subscription_id": subscription_id,
            "project_generation": self._generation(),
        }

    def _unsubscribe(self, params):
        if not isinstance(params, dict) or set(params) != {
            "subscription_id", "project_generation"
        }:
            raise PluginProtocolError(
                "Event unsubscription requires subscription_id and "
                "project_generation."
            )
        self._require_generation(params["project_generation"])
        subscription_id = params["subscription_id"]
        if not isinstance(subscription_id, str) or not subscription_id:
            raise PluginProtocolError(
                "Event subscription IDs must be nonempty strings."
            )
        with self._subscriptionLock:
            removed = self._subscriptions.pop(subscription_id, None)
        return {"removed": removed is not None}

    def _require_generation(self, requested_generation):
        generation = self._generation()
        if (
            isinstance(requested_generation, bool)
            or not isinstance(requested_generation, int)
            or requested_generation != generation
        ):
            raise PluginConflictError(
                "Plugin request targets a stale project generation.",
                {
                    "expected_generation": generation,
                    "actual_generation": requested_generation,
                },
            )

    def _generation(self):
        generation = self.generationSource()
        if isinstance(generation, bool) or not isinstance(generation, int):
            raise RuntimeError("Project generation source returned invalid data.")
        return generation

    @staticmethod
    def _validate_arguments(specification, arguments, keyword_arguments):
        required_count = len(specification.positional)
        maximum_count = required_count + len(specification.optional)
        if not required_count <= len(arguments) <= maximum_count:
            raise PluginProtocolError(
                "{}.{} expects {} required and at most {} positional "
                "arguments; received {}."
                .format(
                    specification.capability,
                    specification.name,
                    required_count,
                    maximum_count,
                    len(arguments),
                )
            )
        allowed_keywords = set(
            specification.optional + specification.keyword
        )
        unknown = set(keyword_arguments) - allowed_keywords
        if unknown:
            raise PluginProtocolError(
                "{}.{} does not accept keyword arguments: {}."
                .format(
                    specification.capability,
                    specification.name,
                    ", ".join(sorted(unknown)),
                )
            )
        supplied_optional = specification.optional[
            :max(0, len(arguments) - required_count)
        ]
        duplicates = set(supplied_optional).intersection(keyword_arguments)
        if duplicates:
            raise PluginProtocolError(
                "{}.{} received arguments twice: {}."
                .format(
                    specification.capability,
                    specification.name,
                    ", ".join(sorted(duplicates)),
                )
            )

    def _current_revision(self, service, specification, arguments):
        if not arguments:
            raise PluginProtocolError(
                "Revision-aware writes require a resource identifier."
            )
        reader = getattr(service, specification.revision_reader, None)
        if not callable(reader):
            raise PluginScopeError(
                "The current project cannot read the resource before writing."
            )
        if specification.revision_reader == "documents":
            resource_id = str(arguments[0])
            values = reader()
            current = next(
                (
                    value for value in values
                    if str(getattr(value, "document_id", "")) == resource_id
                ),
                None,
            )
        else:
            current = reader(arguments[0])
        if current is None:
            raise KeyError(arguments[0])
        return revision_token(current, self.codec)

    def _revisions(self, value):
        revisions = {}
        for item in _walk_records(value):
            key = _record_key(item)
            if key:
                revisions[key] = revision_token(item, self.codec)
        return revisions


def revision_token(value, codec=None):
    codec = codec or api_value_codec()
    canonical = json.dumps(
        codec.encode(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _walk_records(value):
    if is_dataclass(value):
        yield value
        for declared_field in fields(value):
            yield from _walk_records(getattr(value, declared_field.name))
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_records(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_records(item)


def _record_key(value):
    if hasattr(value, "document_id"):
        return "{}:{}".format(
            type(value).__name__, getattr(value, "document_id")
        )
    if hasattr(value, "id"):
        return "{}:{}".format(type(value).__name__, getattr(value, "id"))
    return ""
