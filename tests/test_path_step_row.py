from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@unittest.skipIf(
    importlib.util.find_spec("PySide6") is None,
    "PySide6 app extra is not installed",
)
class PathStepRowTests(unittest.TestCase):
    def test_offscreen_historical_completion_diagnostic_is_bilingual_and_accessible(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtCore import QObject, Property, QEvent, QUrl, Slot
        from PySide6.QtGui import QAccessible, QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine

        from mclab.application.i18n import Translator

        class Backend(QObject):
            def __init__(self, language: str, parent: QObject) -> None:
                super().__init__(parent)
                self._language = language
                self._translator = Translator(language)

            @Property(str, constant=True)
            def language(self) -> str:
                return self._language

            @Slot(str, str, result=str)
            def localizedText(self, _language: str, key: str) -> str:  # noqa: N802
                return self._translator.text(key)

        application = QGuiApplication.instance() or QGuiApplication(
            ["mclab-path-step-row-test"]
        )
        qml_path = ROOT / "src/mclab/application/qml/PathStepRow.qml"
        created: list[QObject] = []
        engines: list[QQmlEngine] = []
        components: list[QQmlComponent] = []

        def create_row(language: str, scenario: dict[str, object]) -> QObject:
            engine = QQmlEngine()
            engines.append(engine)
            backend = Backend(language, application)
            engine.rootContext().setContextProperty("backend", backend)
            component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))
            components.append(component)
            self.assertEqual(
                component.status(),
                QQmlComponent.Ready,
                "\n".join(error.toString() for error in component.errors()),
            )
            item = component.createWithInitialProperties({"scenario": scenario})
            self.assertIsNotNone(
                item,
                "\n".join(error.toString() for error in component.errors()),
            )
            created.append(item)
            return item

        scenario: dict[str, object] = {
            "step": 1,
            "lab": "lab01",
            "title": "Damping",
            "purpose": "Compare damping responses.",
            "completed": True,
            "isNext": False,
            "latestCompletionDecision": {
                "complete": False,
                "primary_reason": "completion.v1.plot_missing",
            },
            "creditedCompletionDecision": {
                "complete": True,
                "primary_reason": "completion.v1.complete",
            },
            "latestRun": r"C:\outputs\newer-incomplete",
            "creditedRun": "/outputs/older-complete",
        }
        expected_by_language = {
            "en": (
                "Done via credited older-complete; latest newer-incomplete: "
                "A required trusted plot is missing"
            ),
            "ko": (
                "이전 완료 인정 older-complete; 최신 newer-incomplete: "
                "필수 신뢰 plot이 없음"
            ),
        }

        try:
            for language, expected in expected_by_language.items():
                with self.subTest(language=language):
                    item = create_row(language, scenario)
                    self.assertTrue(item.property("showsHistoricalDiagnostic"))
                    self.assertEqual(item.property("historicalDiagnosticText"), expected)
                    self.assertEqual(item.property("implicitHeight"), 94.0)

                    label = item.findChild(QObject, "historicalCompletionDiagnostic")
                    self.assertIsNotNone(label)
                    self.assertTrue(label.property("visible"))
                    self.assertEqual(label.property("text"), expected)
                    accessible = QAccessible.queryAccessibleInterface(label)
                    self.assertIsNotNone(accessible)
                    self.assertEqual(accessible.role(), QAccessible.Role.StaticText)
                    self.assertEqual(accessible.text(QAccessible.Text.Name), expected)

            normal_scenario = dict(scenario)
            normal_scenario.update(
                {
                    "latestCompletionDecision": {
                        "complete": True,
                        "primary_reason": "completion.v1.complete",
                    },
                    "latestRun": "/outputs/older-complete",
                }
            )
            normal = create_row("en", normal_scenario)
            self.assertFalse(normal.property("showsHistoricalDiagnostic"))
            self.assertEqual(normal.property("historicalDiagnosticText"), "")
            self.assertEqual(normal.property("implicitHeight"), 74.0)
            normal_label = normal.findChild(
                QObject,
                "historicalCompletionDiagnostic",
            )
            self.assertIsNotNone(normal_label)
            self.assertFalse(normal_label.property("visible"))

            unknown_reason = dict(scenario)
            unknown_reason["latestCompletionDecision"] = {
                "complete": False,
                "primary_reason": "completion.v2.future_reason",
            }
            fallback = create_row("en", unknown_reason)
            self.assertTrue(
                fallback.property("historicalDiagnosticText").endswith(
                    "completion.v2.future_reason"
                )
            )
        finally:
            for item in created:
                item.deleteLater()
            application.sendPostedEvents(None, QEvent.DeferredDelete)
            for component in components:
                component.deleteLater()
            application.sendPostedEvents(None, QEvent.DeferredDelete)
            for engine in engines:
                engine.deleteLater()
            application.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
