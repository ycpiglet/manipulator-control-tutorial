"""Localize runtime failures without hiding copyable technical details."""

from __future__ import annotations


_KO_DETAILS = {
    "Cannot apply an action while completed": "실험이 끝났습니다. 새 실행을 준비한 뒤 조작을 적용합니다.",
    "Cannot apply an action while replaying": "기록 재생 중에는 실험 파라미터를 바꿀 수 없습니다.",
    "Step once requires": "한 단계 실행은 준비 또는 일시정지 상태에서만 사용할 수 있습니다.",
    "No replay is loaded": "재생할 기록이 없습니다.",
    "course comparison is already running": "전체 과정 비교가 이미 실행 중입니다.",
    "active course comparison cannot be deleted": "실행 중인 전체 과정 비교는 삭제할 수 없습니다.",
    "cannot be deleted while an experiment is active": "실험이 열려 있는 동안 저장 결과를 삭제할 수 없습니다.",
    "already running": "다른 실험이 이미 실행 중입니다.",
    "does not contain learner_tuned_config": "이 실행에는 마지막 튜닝 설정이 저장되지 않았습니다.",
    "does not contain a reusable resolved config": "이 실행에는 다시 사용할 확정 설정이 없습니다.",
    "does not identify a scenario": "현재 학습 목록에서 이 실행의 시나리오를 찾지 못했습니다.",
}

_EN_DETAILS = {
    "Cannot apply an action while completed": "The experiment has finished. Start a new run before changing it.",
    "Cannot apply an action while replaying": "Experiment parameters cannot be changed during recording playback.",
    "Step once requires": "Step once is available only while the experiment is ready or paused.",
    "No replay is loaded": "There is no recording to replay.",
    "course comparison is already running": "The course comparison is already running.",
    "active course comparison cannot be deleted": "A running course comparison cannot be deleted.",
    "cannot be deleted while an experiment is active": "Saved evidence cannot be deleted while an experiment is active.",
    "already running": "Another experiment is already running.",
    "does not contain learner_tuned_config": "This run does not include saved tuning values.",
    "does not contain a reusable resolved config": "This run does not include reusable settings.",
    "does not identify a scenario": "This run does not match a scenario in the current learning catalog.",
}

_KO_ACTIONS = {
    "Choose ko or en.": "한국어 또는 영어를 선택하세요.",
    "Open Explore and choose an available scenario.": "탐색에서 사용 가능한 실험을 선택하세요.",
    "Run `python -m mclab doctor`, then retry in safe mode.": "설정 검사를 실행한 뒤 안전 모드로 다시 시도하세요.",
    "Stop it before starting another.": "현재 실험을 마친 뒤 다른 실험을 시작하세요.",
    "Return to the active experiment, or end and save it before starting another.": "실행 중인 실험으로 돌아가거나 종료하고 저장한 뒤 다른 실험을 시작하세요.",
    "Open another saved run or create a fresh run from Explore.": "다른 저장 결과를 열거나 탐색에서 새 실험을 시작하세요.",
    "Use Run again with same settings for this legacy result.": "이 이전 형식 결과는 같은 설정 재실행을 사용하세요.",
    "Run the scenario again to create a fresh recording.": "새 기록을 만들려면 실험을 다시 실행하세요.",
    "Restart the experiment.": "실험 다시 시작을 눌러 주세요.",
    "Pause before stepping once.": "먼저 일시정지한 뒤 한 단계를 실행하세요.",
    "Pause and try the visible-time advance again.": "일시정지한 뒤 0.1초 진행을 다시 눌러 주세요.",
    "Close and reopen the scenario.": "실험을 닫고 다시 열어 주세요.",
    "Choose 0.25×, 0.5×, 1×, or 2×.": "0.25×, 0.5×, 1× 또는 2×를 선택하세요.",
    "Pause the recording and try the timeline again.": "기록을 일시정지하고 타임라인을 다시 조작하세요.",
    "Open a valid recording and select a longer range.": "정상 기록을 열고 더 긴 구간을 선택하세요.",
    "Return to the live experiment before changing controls.": "실험 제어를 바꾸려면 실시간 실험으로 돌아가세요.",
    "Open the path from your file manager.": "파일 관리자에서 해당 경로를 열어 주세요.",
    "Retry with --safe-mode; if it persists, copy these details.": "안전 모드로 다시 시도하고, 계속되면 세부정보를 복사하세요.",
    "Open the experiment again from Explore.": "탐색에서 실험을 다시 열어 주세요.",
    "Open a valid recording and try again.": "정상 기록을 열고 다시 시도하세요.",
    "Use Cancel comparison or wait for the five sets to finish.": "비교 실행 취소를 누르거나 다섯 세트가 끝날 때까지 기다리세요.",
    "Cancel the comparison and wait for it to stop before cleanup.": "비교 실행을 취소하고 완전히 멈춘 뒤 정리하세요.",
}


_BENIGN_SELF_TEST_QT_MESSAGES = (
    "QFontDatabase: Cannot find font directory",
    "Qt no longer ships fonts",
)


def self_test_qt_errors(messages: list[str]) -> list[str]:
    """Return Qt diagnostics that indicate a real QML/application failure."""

    return [
        message
        for message in messages
        if not any(marker in message for marker in _BENIGN_SELF_TEST_QT_MESSAGES)
    ]


def localized_error(language: str, detail: str, action: str) -> tuple[str, str]:
    if language != "ko":
        learner_detail = next(
            (message for fragment, message in _EN_DETAILS.items() if fragment in detail),
            "The request could not be completed.",
        )
        return learner_detail, action
    localized_detail = next(
        (message for fragment, message in _KO_DETAILS.items() if fragment in detail),
        "요청을 처리하지 못했습니다.",
    )
    return localized_detail, _KO_ACTIONS.get(action, action)
