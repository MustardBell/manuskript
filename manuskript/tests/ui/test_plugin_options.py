from manuskript.plugins.api import OptionField, OptionKind
from manuskript.ui.plugins.options import PluginOptionsWidget
from PyQt5.QtWidgets import QGroupBox


def test_generic_plugin_options_widget_round_trips_schema_values():
    widget = PluginOptionsWidget(
        (
            OptionField(
                "enabled",
                "Enabled",
                OptionKind.BOOLEAN,
            ),
            OptionField(
                "count",
                "Count",
                OptionKind.INTEGER,
                minimum=1,
                maximum=10,
            ),
            OptionField(
                "format",
                "Format",
                OptionKind.CHOICE,
                choices=(("One", "one"), ("Two", "two")),
            ),
        ),
        {
            "enabled": True,
            "count": 4,
            "format": "two",
        },
    )

    assert widget.values() == {
        "enabled": True,
        "count": 4,
        "format": "two",
    }


def test_generic_plugin_options_widget_groups_declared_sections():
    widget = PluginOptionsWidget(
        (
            OptionField(
                "heading",
                "Heading",
                default="Welcome",
                section="Welcome",
            ),
            OptionField(
                "topic",
                "Topic",
                default="Topic:",
                section="Thread",
            ),
            OptionField(
                "footer",
                "Footer",
                default="End",
                section="Thread",
            ),
        ),
        {
            "heading": "Hello",
            "topic": "Subject:",
            "footer": "Done",
        },
    )

    assert [
        group.title()
        for group in widget.findChildren(QGroupBox)
    ] == ["Welcome", "Thread"]
    assert widget.values() == {
        "heading": "Hello",
        "topic": "Subject:",
        "footer": "Done",
    }
