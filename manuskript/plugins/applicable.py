"""Which contributions apply here, and in what order.

Two kinds ask this — transforms about a media type, HTML augmentations about
a page type — and both answer it the same way: each contribution decides for
itself whether it applies, and priority decides who goes first.

The registry deliberately does not do this. A catalogue that filters by one
kind of context grows a method per kind of caller: by media type, by page
type, by route, by window. What exists is the registry's question; what
applies is the caller's.
"""


def applicable(contributions, subject=None):
    """The contributions that apply to ``subject``, highest priority first.

    ``subject`` is whatever the contribution's own ``applies_to`` expects: a
    media type for a transform, a page type for an augmentation. Ties break
    on the contribution ID so the order is the same on every run and does not
    depend on which plugin happened to load first.
    """
    return tuple(sorted(
        (
            contribution
            for contribution in contributions
            if contribution.applies_to(subject)
        ),
        key=lambda contribution: (
            -contribution.priority,
            contribution.descriptor.id,
        ),
    ))
