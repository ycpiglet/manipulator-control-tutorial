#!/usr/bin/env python3
"""Capture and score the beginner desktop UI across key edge cases."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

from mclab.application.artifacts import write_manifest
from mclab.application.batch_runs import ALL_COMPARE_ID
from mclab.application.catalog import LEARNING_PATH_SCENARIO_IDS
from mclab.application.visual_semantics import SEMANTIC_COLORS, rgb

TOUR_CONNECTOR_COLOR = "#4F8FF7"


@dataclass(frozen=True)
class AuditCase:
    name: str
    width: int
    height: int
    language: str
    page: str = "home"
    scenario: str | None = None
    actions: str = ""
    expect_error: bool = False
    expect_experiment: bool = False
    expect_non_experiment: bool = False
    action_interval_ms: int = 200
    safe_mode: bool = True
    accessibility: bool = False
    expect_focus_ring: bool = False
    expected_scenario_starts: int | None = None
    expected_disabled_scenario_starts: int | None = None
    required_accessible_names: tuple[str, ...] = ()
    required_descriptions: tuple[str, ...] = ()
    required_description_texts: tuple[str, ...] = ()
    required_enabled_names: tuple[str, ...] = ()
    required_disabled_names: tuple[str, ...] = ()
    required_nonfocusable_names: tuple[str, ...] = ()
    expected_accessible_controls: int | None = None
    require_unique_control_names: bool = False
    forbidden_accessible_names: tuple[str, ...] = ()
    fixture: str = ""
    maximum_actions: int | None = None
    expect_setup_warning: bool = False
    screenshot_ms: int = 1250
    required_scene_tokens: tuple[str, ...] = ()
    minimum_scene_token_pixels: tuple[tuple[str, int], ...] = ()
    minimum_robot_foreground_pixels: int | None = None
    device_scale: float = 1.0
    expected_focus_names: tuple[str, ...] = ()
    expected_speed_trace: tuple[float, ...] = ()
    expected_transport_states: tuple[str, ...] = ()
    expected_pages: tuple[str, ...] = ()
    expected_active_trace: tuple[bool, ...] = ()
    expected_batch_probe_trace: tuple[bool, ...] = ()
    stable_time_trace_pairs: tuple[tuple[int, int], ...] = ()
    expected_cleanup_trace: tuple[bool, ...] = ()
    cleanup_cycle_size: int | None = None
    expect_no_session_replacement: bool = False
    maximum_rss_growth_kb: int | None = None
    rss_ignore_initial_samples: int = 0
    required_now_prompt_fragments: tuple[str, ...] = ()
    maximum_now_prompt_lines: int | None = None
    require_untruncated_now_prompt: bool = False
    expected_evidence_trace: tuple[tuple[bool, bool, bool, int], ...] = ()
    require_evidence_artifact: bool = False
    required_interaction_event_names: tuple[str, ...] = ()
    required_report_texts: tuple[str, ...] = ()
    zero_time_trace_indices: tuple[int, ...] = ()
    positive_time_trace_indices: tuple[int, ...] = ()
    require_no_partially_clipped_controls: bool = False
    auto_quit_grace_ms: int = 2500
    required_in_window_names: tuple[str, ...] = ()
    maximum_primary_actions: int | None = None
    required_primary_names: tuple[str, ...] = ()
    required_context_above_pairs: tuple[tuple[str, str], ...] = ()
    minimum_tour_connector_pixels: int | None = None
    maximum_tour_connector_pixels: int | None = None
    require_camera_gesture_trace: bool = False
    required_control_colors: tuple[tuple[str, str], ...] = ()
    required_control_color_pixels: tuple[tuple[str, str, int], ...] = ()
    required_control_border_colors: tuple[tuple[str, str], ...] = ()
    required_role_border_colors: tuple[tuple[str, str, str, int], ...] = ()
    expected_visible_dialog_names: tuple[str, ...] | None = None
    required_indicator_colors: tuple[tuple[str, str, int], ...] = ()
    required_checked_names: tuple[str, ...] = ()
    required_unchecked_names: tuple[str, ...] = ()
    required_text_metrics: tuple[tuple[str, str, int], ...] = ()
    required_non_overlapping_pairs: tuple[tuple[str, str], ...] = ()
    required_contained_pairs: tuple[tuple[str, str], ...] = ()
    required_single_line_control_names: tuple[str, ...] = ()
    maximum_prediction_horizontal_overflow: float | None = None
    minimum_prediction_vertical_overflow: float | None = None
    maximum_prediction_vertical_overflow: float | None = None
    minimum_prediction_line_count: int | None = None
    maximum_prediction_line_count: int | None = None
    expected_prediction_vertical_scrollbar: bool | None = None
    minimum_prediction_scroll_position: float | None = None
    maximum_prediction_scroll_position: float | None = None
    minimum_prediction_peak_scroll_position: float | None = None
    expected_prediction_input_length: int | None = None
    expected_saved_prediction_length: int | None = None
    maximum_observation_horizontal_overflow: float | None = None
    minimum_observation_vertical_overflow: float | None = None
    maximum_observation_vertical_overflow: float | None = None
    minimum_observation_line_count: int | None = None
    maximum_observation_line_count: int | None = None
    expected_observation_vertical_scrollbar: bool | None = None
    minimum_observation_scroll_position: float | None = None
    maximum_observation_scroll_position: float | None = None
    minimum_observation_peak_scroll_position: float | None = None
    expected_observation_input_length: int | None = None
    expected_saved_observation_length: int | None = None


@dataclass
class AuditResult:
    name: str
    passed: bool
    return_code: int
    screenshot: str
    dimensions: str
    pure_black_pixels: int
    viewport_dark_run: int | None
    focus_yellow_pixels: int | None
    warning_amber_pixels: int | None
    task_action_count: int | None
    accessible_controls: int | None
    unnamed_controls: int | None
    scenario_start_buttons: int | None
    scene_token_distance: dict[str, float] | None
    notes: list[str]
    undersized_targets: int | None = None
    focus_names: list[str] | None = None
    transport_trace: list[dict[str, object]] | None = None
    rss_growth_kb: int | None = None
    primary_actions: int | None = None
    primary_action_names: list[str] | None = None
    tour_connector_pixels: int | None = None
    scenario_context_titles: int | None = None
    control_color_distance: dict[str, float] | None = None
    control_color_pixels: dict[str, int] | None = None
    control_border_color_distance: dict[str, float] | None = None
    role_border_color_pixels: dict[str, int] | None = None
    indicator_color_pixels: dict[str, int] | None = None
    text_metric_values: dict[str, dict[str, float]] | None = None
    control_text_vertical_spans: dict[str, float] | None = None
    scene_token_pixels: dict[str, int] | None = None
    robot_foreground_pixels: int | None = None
    prediction_text_layout: dict[str, float | bool] | None = None
    observation_text_layout: dict[str, float | bool] | None = None


CASES = (
    AuditCase("home_640_ko", 640, 360, "ko"),
    AuditCase(
        "home_focus_640_ko",
        640,
        360,
        "ko",
        actions="key_tab",
        expect_focus_ring=True,
        expected_focus_names=("홈",),
    ),
    AuditCase(
        "home_first_view_onboarding_640_ko",
        640,
        360,
        "ko",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "시작",
            "값 변경",
            "기록 재생",
            "건너뛰기",
            "다음 실험 시작",
        ),
        required_in_window_names=(
            "시작",
            "값 변경",
            "기록 재생",
            "건너뛰기",
            "다음 실험 시작",
        ),
        expected_accessible_controls=7,
        require_unique_control_names=True,
        require_no_partially_clipped_controls=True,
        maximum_tour_connector_pixels=0,
        required_control_border_colors=(("건너뛰기", "#64748B"),),
        required_text_metrics=((
            "자동 데모 조건에서 질량·스프링·감쇠 응답을 관찰하고 저장된 증거를 비교합니다.",
            "#334155",
            17,
        ),),
    ),
    AuditCase(
        "home_tour_skip_focus_640_ko",
        640,
        360,
        "ko",
        actions="focus_tour_skip,key_enter,record_focus,accessibility_snapshot",
        action_interval_ms=400,
        accessibility=True,
        expect_focus_ring=True,
        expected_focus_names=("건너뛰기", "다음 실험 시작", "다음 실험 시작"),
        required_accessible_names=(
            "둘러보기 다시 보기",
            "실험 환경 상태 · 설정 준비 완료",
            "다음 실험 시작",
        ),
        required_in_window_names=(
            "둘러보기 다시 보기",
            "실험 환경 상태 · 설정 준비 완료",
            "다음 실험 시작",
        ),
        expected_accessible_controls=7,
        require_unique_control_names=True,
        require_no_partially_clipped_controls=True,
        screenshot_ms=2400,
        required_control_border_colors=(("둘러보기 다시 보기", "#64748B"),),
    ),
    AuditCase(
        "home_tour_reopen_focus_640_ko",
        640,
        360,
        "ko",
        actions=(
            "focus_tour_skip,key_enter,focus_tour_again,key_enter,record_focus,"
            "accessibility_snapshot"
        ),
        action_interval_ms=400,
        accessibility=True,
        expect_focus_ring=True,
        expected_focus_names=(
            "건너뛰기",
            "다음 실험 시작",
            "둘러보기 다시 보기",
            "건너뛰기",
            "건너뛰기",
        ),
        required_accessible_names=(
            "시작",
            "값 변경",
            "기록 재생",
            "건너뛰기",
            "다음 실험 시작",
        ),
        required_in_window_names=(
            "시작",
            "값 변경",
            "기록 재생",
            "건너뛰기",
            "다음 실험 시작",
        ),
        expected_accessible_controls=7,
        require_unique_control_names=True,
        require_no_partially_clipped_controls=True,
        screenshot_ms=3000,
    ),
    AuditCase(
        "home_first_view_onboarding_1280_en",
        1280,
        720,
        "en",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Start an experiment",
            "Change one parameter",
            "Replay your recording",
            "Skip tour",
            "Start next experiment",
        ),
        required_in_window_names=(
            "Start an experiment",
            "Change one parameter",
            "Replay your recording",
            "Skip tour",
            "Start next experiment",
        ),
        expected_accessible_controls=7,
        require_unique_control_names=True,
        require_no_partially_clipped_controls=True,
        minimum_tour_connector_pixels=300,
        maximum_tour_connector_pixels=1_100,
    ),
    AuditCase(
        "home_first_view_onboarding_200pct_en",
        640,
        360,
        "en",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Start",
            "Change",
            "Replay",
            "Skip",
            "Start next experiment",
        ),
        required_in_window_names=(
            "Start",
            "Change",
            "Replay",
            "Skip",
            "Start next experiment",
        ),
        expected_accessible_controls=7,
        require_unique_control_names=True,
        require_no_partially_clipped_controls=True,
        device_scale=2.0,
        maximum_tour_connector_pixels=0,
    ),
    AuditCase(
        "home_missing_asset_640_ko",
        640,
        360,
        "ko",
        actions="inject_missing_next_asset,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("설정 검토", "다음 실험 시작"),
        required_descriptions=("다음 실험 시작",),
        expect_setup_warning=True,
    ),
    AuditCase(
        "first_run_one_action_640_ko",
        640,
        360,
        "ko",
        actions="start_next",
        expect_experiment=True,
        maximum_actions=1,
    ),
    AuditCase(
        "first_run_guided_control_640_ko",
        640,
        360,
        "ko",
        actions="start_next,record_backend,record_focus,accessibility_snapshot",
        action_interval_ms=500,
        accessibility=True,
        expect_experiment=True,
        required_accessible_names=(
            "LAB01 · 자동 데모 · 일시정지",
            "실험: 밀기",
            "감쇠",
            "감쇠: 2.0 N·s/m",
            "재생",
            "스프링",
            "댐퍼",
            "질량 블록",
            "평형점",
        ),
        required_descriptions=("감쇠",),
        required_description_texts=("현재 2.0 N·s/m",),
        required_text_metrics=(("감쇠: 2.0 N·s/m", "#1D4ED8", 17),),
        required_now_prompt_fragments=("밀기", "감쇠"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        expected_transport_states=("paused",),
        expected_active_trace=(True,),
        expected_focus_names=("실험: 밀기",),
        zero_time_trace_indices=(0,),
        required_scene_tokens=("current", "spring"),
        maximum_primary_actions=1,
        required_primary_names=("실험: 밀기",),
        screenshot_ms=1900,
    ),
    AuditCase(
        "first_run_guided_sequence_640_ko",
        640,
        360,
        "ko",
        actions=(
            "start_next,push,control_damping=6.0,record_backend,pause,"
            "wait_session_completed,wait_worker,navigate_results,replay_last_output,"
            "pause,record_backend,accessibility_snapshot"
        ),
        action_interval_ms=500,
        accessibility=True,
        expect_experiment=True,
        required_accessible_names=(
            "처음 프레임",
            "이전",
            "재생",
            "다음 프레임",
            "마지막 프레임",
            "기록 재생 타임라인",
        ),
        required_descriptions=("기록 재생 타임라인",),
        required_now_prompt_fragments=("타임라인", "현재 표시", "목표 표시"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        expected_transport_states=("paused", "paused"),
        expected_pages=("experiment", "experiment"),
        expected_active_trace=(True, True),
        zero_time_trace_indices=(0,),
        expected_evidence_trace=(
            (False, False, False, 2),
            (False, False, False, 4),
        ),
        required_interaction_event_names=("push", "damping"),
        screenshot_ms=14_000,
        auto_quit_grace_ms=8_000,
    ),
    AuditCase(
        "home_1280_en",
        1280,
        720,
        "en",
        minimum_tour_connector_pixels=300,
        maximum_tour_connector_pixels=1_100,
    ),
    AuditCase(
        "home_1920_ko",
        1920,
        1080,
        "ko",
        minimum_tour_connector_pixels=800,
        maximum_tour_connector_pixels=2_600,
    ),
    AuditCase(
        "home_200pct_ko",
        640,
        360,
        "ko",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("다음 실험 시작",),
        required_descriptions=("다음 실험 시작",),
        device_scale=2.0,
    ),
    AuditCase(
        "home_complete_640_ko",
        640,
        360,
        "ko",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="path_complete",
        required_accessible_names=("결과 검토",),
        required_descriptions=("결과 검토",),
        forbidden_accessible_names=("다음 실험 시작",),
        require_unique_control_names=True,
    ),
    AuditCase(
        "home_batch_priority_640_ko",
        640,
        360,
        "ko",
        actions="inject_batch_running,accessibility_snapshot",
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=("전체 과정 비교 실행 중", "비교 실행 취소"),
        required_in_window_names=("전체 과정 비교 실행 중", "비교 실행 취소"),
        forbidden_accessible_names=("건너뛰기",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
        require_no_partially_clipped_controls=True,
    ),
    AuditCase(
        "path_640_ko",
        640,
        360,
        "ko",
        page="path",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("다음 실험 시작: LAB01 · 자동 데모",),
        required_descriptions=("다음 실험 시작: LAB01 · 자동 데모",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
    ),
    AuditCase(
        "path_partial_1280_en",
        1280,
        720,
        "en",
        page="path",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="path_partial",
        required_accessible_names=("Start next experiment: LAB02 · Auto demo",),
        required_descriptions=("Start next experiment: LAB02 · Auto demo",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
    ),
    AuditCase(
        "path_complete_640_ko",
        640,
        360,
        "ko",
        page="path",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="path_complete",
        required_accessible_names=("결과 검토",),
        forbidden_accessible_names=("다음 실험 시작: LAB04 · 가상 벽",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
    ),
    AuditCase(
        "path_batch_next_640_ko",
        640,
        360,
        "ko",
        page="path",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="path_scenarios_complete",
        required_accessible_names=("전체 비교 시작: 과정 · 전체 과정 비교",),
        required_descriptions=("전체 비교 시작: 과정 · 전체 과정 비교",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
    ),
    AuditCase(
        "path_batch_running_640_ko",
        640,
        360,
        "ko",
        page="path",
        actions="inject_batch_running,accessibility_snapshot",
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=("비교 실행 취소: 과정 · 전체 과정 비교",),
        required_descriptions=("비교 실행 취소: 과정 · 전체 과정 비교",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
    ),
    AuditCase(
        "path_batch_cancelling_640_ko",
        640,
        360,
        "ko",
        page="path",
        actions="inject_batch_cancelling,accessibility_snapshot",
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=("중단 중…: 과정 · 전체 과정 비교",),
        required_disabled_names=("중단 중…: 과정 · 전체 과정 비교",),
        required_description_texts=("비교 실행을 중단하는 중",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
    ),
    AuditCase(
        "path_batch_language_switch_640_en",
        640,
        360,
        "ko",
        page="path",
        actions="inject_batch_running,language_en,accessibility_snapshot",
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=(
            "Home",
            "Learning path",
            "Explore",
            "Results",
            "Cancel comparison: COURSE · Compare the course",
        ),
        required_description_texts=("Set 2/5 · PID control",),
        forbidden_accessible_names=("홈", "학습 경로", "탐색", "결과"),
        expected_accessible_controls=6,
        require_unique_control_names=True,
    ),
    AuditCase(
        "path_batch_duplicate_640_ko",
        640,
        360,
        "ko",
        page="path",
        actions="inject_batch_running,start_next,accessibility_snapshot",
        expect_error=True,
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=("세부정보 복사", "닫기"),
        required_descriptions=("세부정보 복사",),
    ),
    AuditCase(
        "path_missing_next_640_ko",
        640,
        360,
        "ko",
        page="path",
        actions="inject_missing_next_asset,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("다음 실험 시작: LAB01 · 자동 데모",),
        required_descriptions=("다음 실험 시작: LAB01 · 자동 데모",),
        expected_accessible_controls=6,
        require_unique_control_names=True,
        expect_setup_warning=True,
    ),
    AuditCase("explore_640_en", 640, 360, "en", page="explore"),
    AuditCase(
        "explore_filters_640_ko",
        640,
        360,
        "ko",
        page="explore",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "시나리오 검색",
            "난이도 필터",
            "방식 필터",
            "72개 중 72개 표시",
        ),
        required_descriptions=("시나리오 검색", "난이도 필터", "방식 필터"),
        expected_scenario_starts=72,
        require_no_partially_clipped_controls=True,
        required_in_window_names=("LAB01 · 저감쇠",),
        required_control_colors=(
            ("시나리오 검색", "#5B6475"),
            ("시나리오 검색", "#64748B"),
        ),
        required_text_metrics=((
            "자동 데모 조건에서 질량·스프링·감쇠 응답을 관찰하고 저장된 증거를 비교합니다.",
            "#475569",
            17,
        ),),
    ),
    AuditCase(
        "explore_hands_on_filter_640_en",
        640,
        360,
        "en",
        page="explore",
        actions="explore_filter_hands_on,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("9 of 72 shown", "Mode filter"),
        expected_scenario_starts=9,
        require_no_partially_clipped_controls=True,
    ),
    AuditCase(
        "explore_search_contrast_200pct_ko",
        640,
        360,
        "ko",
        page="explore",
        actions="accessibility_snapshot",
        accessibility=True,
        device_scale=2.0,
        expected_scenario_starts=72,
        require_no_partially_clipped_controls=True,
        required_control_colors=(
            ("시나리오 검색", "#5B6475"),
            ("시나리오 검색", "#64748B"),
        ),
    ),
    AuditCase(
        "explore_multi_term_search_640_en",
        640,
        360,
        "en",
        page="explore",
        actions="type_explore_lab04_wall,accessibility_snapshot",
        accessibility=True,
        expected_focus_names=("Search scenarios",),
        required_accessible_names=("14 of 72 shown", "Search scenarios"),
        expected_scenario_starts=14,
        expect_focus_ring=True,
        require_no_partially_clipped_controls=True,
        action_interval_ms=500,
        screenshot_ms=2600,
    ),
    AuditCase(
        "explore_multi_term_search_200pct_en",
        640,
        360,
        "en",
        page="explore",
        actions="type_explore_lab04_wall,accessibility_snapshot",
        accessibility=True,
        expected_focus_names=("Search scenarios",),
        required_accessible_names=("14 of 72 shown", "Search scenarios"),
        expected_scenario_starts=14,
        expect_focus_ring=True,
        require_no_partially_clipped_controls=True,
        device_scale=2.0,
        action_interval_ms=500,
        screenshot_ms=2600,
    ),
    AuditCase(
        "explore_combined_filter_640_ko",
        640,
        360,
        "ko",
        page="explore",
        actions="explore_filter_build,explore_filter_hands_on,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("72개 중 2개 표시", "난이도 필터", "방식 필터"),
        expected_scenario_starts=2,
        require_no_partially_clipped_controls=True,
        action_interval_ms=500,
        screenshot_ms=6000,
        auto_quit_grace_ms=2500,
    ),
    AuditCase(
        "explore_empty_filter_640_ko",
        640,
        360,
        "ko",
        page="explore",
        actions="explore_search_none,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "72개 중 0개 표시",
            "조건에 맞는 실험이 없습니다",
            "필터 초기화",
        ),
        required_descriptions=("필터 초기화",),
        expected_scenario_starts=0,
        require_no_partially_clipped_controls=True,
    ),
    AuditCase(
        "explore_filter_keyboard_640_ko",
        640,
        360,
        "ko",
        page="explore",
        actions="focus_scenario_search,key_tab,key_tab",
        expected_focus_names=("시나리오 검색", "난이도 필터", "방식 필터"),
        expect_focus_ring=True,
        action_interval_ms=300,
    ),
    AuditCase(
        "explore_card_keyboard_scroll_640_ko",
        640,
        360,
        "ko",
        page="explore",
        actions=(
            "focus_scenario_search,key_tab,key_tab,key_tab,key_tab,key_tab,key_tab,"
            "key_backtab,key_backtab,key_backtab,key_backtab"
        ),
        expect_focus_ring=True,
        expected_focus_names=(
            "시나리오 검색",
            "난이도 필터",
            "방식 필터",
            "시작: LAB01 · 자동 데모",
            "시작: LAB01 · 저감쇠",
            "시작: LAB01 · 과감쇠",
            "시작: LAB01 · 높은 강성",
            "시작: LAB01 · 과감쇠",
            "시작: LAB01 · 저감쇠",
            "시작: LAB01 · 자동 데모",
            "방식 필터",
        ),
        action_interval_ms=300,
        screenshot_ms=4500,
    ),
    AuditCase(
        "explore_empty_clear_keyboard_640_ko",
        640,
        360,
        "ko",
        page="explore",
        actions="explore_search_none,focus_explore_clear,key_enter,accessibility_snapshot",
        accessibility=True,
        expected_focus_names=("필터 초기화", "시나리오 검색"),
        required_accessible_names=("72개 중 72개 표시", "시나리오 검색"),
        expected_scenario_starts=72,
        expect_focus_ring=True,
        action_interval_ms=500,
        screenshot_ms=5000,
        auto_quit_grace_ms=2500,
    ),
    AuditCase(
        "explore_accessibility_1280_en",
        1280,
        720,
        "en",
        page="explore",
        actions="accessibility_snapshot",
        accessibility=True,
        expected_scenario_starts=72,
        required_control_colors=(
            ("Search scenarios", "#5B6475"),
            ("Search scenarios", "#64748B"),
        ),
    ),
    AuditCase(
        "language_switch_explore_1280",
        1280,
        720,
        "en",
        page="explore",
        actions="language_ko,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "홈",
            "학습 경로",
            "탐색",
            "결과",
            "시나리오 검색",
            "난이도 필터",
            "방식 필터",
            "시작: LAB01 · 자동 데모",
        ),
        forbidden_accessible_names=("Home", "Learning path", "Explore", "Results"),
        expected_scenario_starts=72,
    ),
    AuditCase(
        "results_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("첫 실험 시작",),
        required_descriptions=("첫 실험 시작",),
    ),
    AuditCase(
        "results_valid_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=(
            "리포트 보기: LAB01 · 직접 조작 · 최신",
            "기록 재생: LAB01 · 직접 조작 · 최신",
            "관리: LAB01 · 직접 조작 · 최신",
            "최대 변위",
            "기록 시간",
            "학습자 조작",
        ),
        required_descriptions=(
            "리포트 보기: LAB01 · 직접 조작 · 최신",
            "기록 재생: LAB01 · 직접 조작 · 최신",
        ),
        forbidden_accessible_names=("lab01.interactive-pull",),
        required_text_metrics=(
            ("최대 변위", "#475569", 17),
            ("기록 시간", "#475569", 17),
            ("학습자 조작", "#475569", 17),
        ),
    ),
    AuditCase(
        "results_valid_1280_en",
        1280,
        720,
        "en",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=(
            "View report: LAB01 · Interactive · Latest",
            "Replay recording: LAB01 · Interactive · Latest",
            "Manage: LAB01 · Interactive · Latest",
        ),
        required_descriptions=(
            "View report: LAB01 · Interactive · Latest",
            "Replay recording: LAB01 · Interactive · Latest",
        ),
        maximum_primary_actions=1,
        required_primary_names=(
            "Replay recording: LAB01 · Interactive · Latest",
        ),
        required_control_border_colors=(
            ("View report: LAB01 · Interactive · Latest", "#64748B"),
            ("Manage: LAB01 · Interactive · Latest", "#64748B"),
        ),
        required_text_metrics=(
            ("Peak displacement", "#475569", 17),
            ("Recorded time", "#475569", 17),
            ("Learner actions", "#475569", 17),
        ),
    ),
    AuditCase(
        "results_valid_200pct_ko",
        640,
        360,
        "ko",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=(
            "최대 변위",
            "기록 시간",
            "학습자 조작",
        ),
        required_in_window_names=(
            "최대 변위",
            "기록 시간",
            "학습자 조작",
        ),
        required_text_metrics=(
            ("최대 변위", "#475569", 17),
            ("기록 시간", "#475569", 17),
            ("학습자 조작", "#475569", 17),
        ),
        require_no_partially_clipped_controls=True,
        device_scale=2.0,
    ),
    AuditCase(
        "batch_running_results_replay_guard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=("기록 재생: LAB01 · 직접 조작 · 최신",),
        required_disabled_names=("기록 재생: LAB01 · 직접 조작 · 최신",),
        required_description_texts=(
            "위의 전체 비교를 취소하거나 완료될 때까지 기다린 뒤 저장 기록을 여세요.",
        ),
    ),
    AuditCase(
        "batch_running_empty_results_guard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("첫 실험 시작",),
        required_disabled_names=("첫 실험 시작",),
        required_description_texts=(
            "위의 전체 비교를 취소하거나 완료될 때까지 기다린 뒤 새 실험을 시작하세요.",
        ),
        require_no_partially_clipped_controls=True,
    ),
    AuditCase(
        "results_batch_complete_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="path_complete",
        required_accessible_names=(
            "리포트 보기: 과정 · 전체 과정 비교 · 최신",
            "전체 비교 다시 실행: 과정 · 전체 과정 비교 · 최신",
            "관리: 과정 · 전체 과정 비교 · 최신",
            "비교 세트",
            "시나리오 실행",
        ),
        required_descriptions=("전체 비교 다시 실행: 과정 · 전체 과정 비교 · 최신",),
    ),
    AuditCase(
        "results_batch_running_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,accessibility_snapshot",
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=(
            "비교 실행 취소: 과정 · 전체 과정 비교 · 최신",
            "관리: 과정 · 전체 과정 비교 · 최신",
        ),
        required_descriptions=("비교 실행 취소: 과정 · 전체 과정 비교 · 최신",),
        required_disabled_names=("관리: 과정 · 전체 과정 비교 · 최신",),
    ),
    AuditCase(
        "results_batch_stale_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=(
            "중단됨",
            "전체 비교 다시 실행: 과정 · 전체 과정 비교 · 최신",
        ),
        forbidden_accessible_names=("비교 실행 취소: 과정 · 전체 과정 비교 · 최신",),
    ),
    AuditCase(
        "results_batch_delete_guard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,delete_active_batch,accessibility_snapshot",
        expect_error=True,
        accessibility=True,
        fixture="path_batch_running",
        required_accessible_names=("세부정보 복사", "닫기"),
        required_descriptions=("세부정보 복사",),
    ),
    AuditCase(
        "results_many_1280_en",
        1280,
        720,
        "en",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="many_results",
        required_accessible_names=(
            "Rerun same settings: LAB01 · Auto demo · Latest",
            "View report: LAB01 · Auto demo · Latest",
            "Manage: LAB01 · Auto demo · Older 20",
            "Show 20 more",
        ),
        forbidden_accessible_names=(
            "Replay recording: LAB01 · Auto demo · Latest",
        ),
        expected_accessible_controls=66,
        require_unique_control_names=True,
        maximum_primary_actions=1,
        required_primary_names=(
            "Rerun same settings: LAB01 · Auto demo · Latest",
        ),
    ),
    AuditCase(
        "results_many_keyboard_scroll_640_en",
        640,
        360,
        "en",
        page="results",
        actions=(
            "focus_result_primary,key_tab,key_tab,key_tab,key_tab,key_tab,key_tab,"
            "key_backtab,key_backtab,key_backtab,key_backtab,accessibility_snapshot"
        ),
        expect_focus_ring=True,
        accessibility=True,
        fixture="many_results",
        expected_focus_names=(
            "Rerun same settings: LAB01 · Auto demo · Latest",
            "View report: LAB01 · Auto demo · Latest",
            "Manage: LAB01 · Auto demo · Latest",
            "Rerun same settings: LAB01 · Auto demo · Older 2",
            "View report: LAB01 · Auto demo · Older 2",
            "Manage: LAB01 · Auto demo · Older 2",
            "Rerun same settings: LAB01 · Auto demo · Older 3",
            "Manage: LAB01 · Auto demo · Older 2",
            "View report: LAB01 · Auto demo · Older 2",
            "Rerun same settings: LAB01 · Auto demo · Older 2",
            "Manage: LAB01 · Auto demo · Latest",
        ),
        required_in_window_names=(
            "LAB01 · Auto demo · Latest",
        ),
        required_context_above_pairs=((
            "LAB01 · Auto demo · Latest",
            "Manage: LAB01 · Auto demo · Latest",
        ),),
        action_interval_ms=300,
        screenshot_ms=4500,
    ),
    AuditCase(
        "results_many_load_1280_en",
        1280,
        720,
        "en",
        page="results",
        actions="load_more_results,accessibility_snapshot",
        accessibility=True,
        fixture="many_results",
        required_accessible_names=(
            "View report: LAB01 · Auto demo · Older 21",
            "Manage: LAB01 · Auto demo · Older 40",
            "Show 20 more",
        ),
        expected_accessible_controls=126,
        require_unique_control_names=True,
        maximum_primary_actions=1,
        required_primary_names=(
            "Rerun same settings: LAB01 · Auto demo · Latest",
        ),
        screenshot_ms=1450,
    ),
    AuditCase(
        "results_many_load_keyboard_640_en",
        640,
        360,
        "en",
        page="results",
        actions=(
            "focus_results_load_more,press_enter,record_focus,"
            "focus_results_load_more,press_enter,record_focus,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        fixture="many_results",
        expected_focus_names=(
            "Show 20 more",
            "Rerun same settings: LAB01 · Auto demo · Older 21",
            "Show 20 more",
            "Rerun same settings: LAB01 · Auto demo · Older 41",
        ),
        required_accessible_names=(
            "Rerun same settings: LAB01 · Auto demo · Older 41",
            "Manage: LAB01 · Auto demo · Older 60",
        ),
        forbidden_accessible_names=("Show 20 more",),
        expected_accessible_controls=185,
        require_unique_control_names=True,
        required_in_window_names=(
            "LAB01 · Auto demo · Older 41",
        ),
        required_context_above_pairs=((
            "LAB01 · Auto demo · Older 41",
            "Rerun same settings: LAB01 · Auto demo · Older 41",
        ),),
        action_interval_ms=400,
        screenshot_ms=4300,
    ),
    AuditCase(
        "results_manage_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="open_result_manager,record_focus,accessibility_snapshot",
        accessibility=True,
        expect_focus_ring=True,
        fixture="valid_replay",
        required_accessible_names=(
            "같은 설정 재실행",
            "마지막 튜닝으로 실행",
            "폴더 열기",
            "저장 실행을 복구 보관소로 이동",
        ),
        required_descriptions=("저장 실행을 복구 보관소로 이동",),
        expected_focus_names=("닫기",),
        required_control_border_colors=(("폴더 열기", "#64748B"),),
        required_role_border_colors=((
            "Dialog", "저장 실행 상세와 정리", "#64748B", 1_000,
        ),),
        expected_visible_dialog_names=("저장 실행 상세와 정리",),
        action_interval_ms=400,
        screenshot_ms=1900,
    ),
    AuditCase(
        "results_manage_200pct_en",
        640,
        360,
        "en",
        page="results",
        actions="open_result_manager,record_focus,accessibility_snapshot",
        accessibility=True,
        expect_focus_ring=True,
        fixture="valid_replay",
        device_scale=2.0,
        required_accessible_names=(
            "Rerun same settings",
            "Run last tuning",
            "Open folder",
            "Move saved run to quarantine",
        ),
        required_descriptions=("Move saved run to quarantine",),
        required_in_window_names=(
            "Rerun same settings",
            "Open folder",
            "Move saved run to quarantine",
            "Close",
        ),
        require_no_partially_clipped_controls=True,
        expected_focus_names=("Close",),
        required_role_border_colors=((
            "Dialog", "Saved run details and cleanup", "#64748B", 2_000,
        ),),
        expected_visible_dialog_names=("Saved run details and cleanup",),
        action_interval_ms=400,
        screenshot_ms=1900,
    ),
    AuditCase(
        "results_quarantine_confirm_wrong_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions=(
            "open_result_manager,begin_result_quarantine,"
            "type_wrong_result_confirmation,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        fixture="valid_replay",
        required_accessible_names=(
            "이 실행을 옮기려면 정확한 폴더명을 입력하세요: valid_replay",
            "복구 보관소 이동 확인",
            "뒤로",
        ),
        required_disabled_names=("복구 보관소 이동 확인",),
        required_description_texts=("정확한 저장 실행 폴더명",),
        expected_focus_names=(
            "이 실행을 옮기려면 정확한 폴더명을 입력하세요: valid_replay",
        ),
        required_in_window_names=(
            "복구 보관소 이동 확인",
            "뒤로",
        ),
        require_no_partially_clipped_controls=True,
        action_interval_ms=400,
        screenshot_ms=2200,
    ),
    AuditCase(
        "results_quarantine_confirm_exact_200pct_en",
        640,
        360,
        "en",
        page="results",
        actions=(
            "open_result_manager,begin_result_quarantine,"
            "type_result_confirmation,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        fixture="valid_replay",
        device_scale=2.0,
        required_accessible_names=(
            "Type the exact folder name to move this run: valid_replay",
            "Confirm quarantine",
            "Back",
        ),
        required_enabled_names=("Confirm quarantine", "Back"),
        required_description_texts=("Exact saved-run folder name",),
        expected_focus_names=(
            "Type the exact folder name to move this run: valid_replay",
        ),
        required_in_window_names=("Confirm quarantine", "Back"),
        require_no_partially_clipped_controls=True,
        action_interval_ms=400,
        screenshot_ms=2200,
    ),
    AuditCase(
        "results_manage_focus_return_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions=(
            "open_result_manager,record_focus,key_tab,key_tab,key_tab,key_tab,key_tab,"
            "key_escape,record_focus"
        ),
        fixture="valid_replay",
        expect_focus_ring=True,
        expected_focus_names=(
            "닫기",
            "같은 설정 재실행",
            "폴더 열기",
            "저장 실행을 복구 보관소로 이동",
            "닫기",
            "같은 설정 재실행",
            "관리: LAB01 · 직접 조작 · 최신",
            "관리: LAB01 · 직접 조작 · 최신",
        ),
        action_interval_ms=300,
        screenshot_ms=3100,
    ),
    AuditCase(
        "results_delete_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="open_result_manager,delete_managed_result,accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=("첫 실험 시작",),
        required_descriptions=("첫 실험 시작",),
        forbidden_accessible_names=(
            "리포트 보기: LAB01 · 직접 조작 · 최신",
            "기록 재생: LAB01 · 직접 조작 · 최신",
            "관리: LAB01 · 직접 조작 · 최신",
        ),
        screenshot_ms=1500,
    ),
    AuditCase(
        "results_corrupt_replay_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="accessibility_snapshot",
        accessibility=True,
        fixture="corrupt_replay",
        required_accessible_names=(
            "같은 설정 재실행: LAB01 · 자동 데모 · 최신",
            "관리: LAB01 · 자동 데모 · 최신",
        ),
        required_descriptions=(
            "같은 설정 재실행: LAB01 · 자동 데모 · 최신",
        ),
        required_enabled_names=(
            "같은 설정 재실행: LAB01 · 자동 데모 · 최신",
        ),
        forbidden_accessible_names=(
            "리포트 보기: LAB01 · 자동 데모 · 최신",
            "기록 재생: LAB01 · 자동 데모 · 최신",
        ),
        expected_accessible_controls=7,
        maximum_primary_actions=1,
        required_primary_names=(
            "같은 설정 재실행: LAB01 · 자동 데모 · 최신",
        ),
    ),
    AuditCase(
        "batch_running_results_rerun_guard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,accessibility_snapshot",
        accessibility=True,
        fixture="corrupt_replay",
        required_accessible_names=(
            "같은 설정 재실행: LAB01 · 자동 데모 · 최신",
        ),
        required_disabled_names=(
            "같은 설정 재실행: LAB01 · 자동 데모 · 최신",
        ),
        required_description_texts=(
            "위의 전체 비교를 취소하거나 완료될 때까지 기다린 뒤 새 실험을 시작하세요.",
        ),
        forbidden_accessible_names=(
            "기록 재생: LAB01 · 자동 데모 · 최신",
        ),
        expected_accessible_controls=9,
    ),
    AuditCase(
        "results_missing_replay_rerun_keyboard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions=(
            "focus_result_primary,key_enter,record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        expect_experiment=True,
        fixture="corrupt_replay",
        expected_pages=("experiment",),
        expected_active_trace=(True,),
        screenshot_ms=2400,
    ),
    AuditCase(
        "replay_flow_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="replay_fixture,pause,seek_50,toggle_loop,record_backend,accessibility_snapshot",
        accessibility=True,
        expect_experiment=True,
        fixture="valid_replay",
        required_accessible_names=(
            "복습: 타임라인을 움직여 현재 표시와 목표 표시가 달라지는 순간을 찾으세요.",
            "처음 프레임",
            "이전",
            "재생",
            "다음 프레임",
            "마지막 프레임",
            "구간 반복",
            "반복 구간",
            "기록 재생 타임라인",
            "조작 이벤트: push · 0.25 s",
            "조작 이벤트: damping · 0.75 s",
            "프레임 31 / 61 · 0.50 s",
        ),
        required_descriptions=(
            "기록 재생 타임라인",
            "반복 구간",
            "조작 이벤트: push · 0.25 s",
            "조작 이벤트: damping · 0.75 s",
        ),
        required_enabled_names=("반복 구간",),
        forbidden_accessible_names=("실험: 당기기", "실험: 밀기", "질량"),
        required_now_prompt_fragments=("타임라인", "현재 표시", "목표 표시"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        required_non_overlapping_pairs=((
            "기록 재생 타임라인",
            "프레임 31 / 61 · 0.50 s",
        ),),
        required_text_metrics=(
            ("프레임 31 / 61 · 0.50 s", "#334155", 17),
            (
                "물리를 다시 계산하지 않고 저장된 상태를 표시합니다. "
                "타임라인이나 프레임 버튼으로 증거를 살펴보세요.",
                "#334155",
                17,
            ),
        ),
        maximum_primary_actions=1,
        required_primary_names=("재생",),
        screenshot_ms=1600,
    ),
    AuditCase(
        "replay_timeline_keyboard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions=(
            "replay_fixture,pause,first_frame,key_backtab,key_backtab,key_backtab,"
            "key_backtab,key_backtab,record_focus,key_right,record_focus,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        expect_experiment=True,
        expect_focus_ring=True,
        fixture="valid_replay",
        required_accessible_names=(
            "기록 재생 타임라인",
            "프레임 7 / 61 · 0.10 s",
        ),
        required_descriptions=("기록 재생 타임라인",),
        expected_focus_names=(
            "이전",
            "처음 프레임",
            "조작 이벤트: damping · 0.75 s",
            "조작 이벤트: push · 0.25 s",
            "기록 재생 타임라인",
            "기록 재생 타임라인",
            "기록 재생 타임라인",
            "기록 재생 타임라인",
        ),
        action_interval_ms=300,
        screenshot_ms=4000,
    ),
    AuditCase(
        "replay_last_boundary_640_en",
        640,
        360,
        "en",
        page="results",
        actions="replay_fixture,pause,last_frame,next_frame,accessibility_snapshot",
        accessibility=True,
        expect_experiment=True,
        fixture="valid_replay",
        required_accessible_names=(
            "Frame 61 / 61 · 1.00 s",
            "Play",
            "Last frame",
            "Next frame",
        ),
        required_text_metrics=(("Frame 61 / 61 · 1.00 s", "#334155", 17),),
        required_non_overlapping_pairs=((
            "Replay timeline",
            "Frame 61 / 61 · 1.00 s",
        ),),
        screenshot_ms=1700,
    ),
    AuditCase(
        "replay_timeline_200pct_en",
        640,
        360,
        "en",
        page="results",
        actions="replay_fixture,pause,last_frame,accessibility_snapshot",
        accessibility=True,
        expect_experiment=True,
        fixture="valid_replay",
        required_accessible_names=(
            "Replay timeline",
            "Frame 61 / 61 · 1.00 s",
        ),
        required_in_window_names=(
            "Replay timeline",
            "Frame 61 / 61 · 1.00 s",
        ),
        required_text_metrics=(("Frame 61 / 61 · 1.00 s", "#334155", 17),),
        required_non_overlapping_pairs=((
            "Replay timeline",
            "Frame 61 / 61 · 1.00 s",
        ),),
        device_scale=2.0,
        screenshot_ms=1700,
    ),
    AuditCase(
        "replay_event_jump_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="replay_fixture,pause,activate_event_0,accessibility_snapshot",
        accessibility=True,
        expect_experiment=True,
        fixture="valid_replay",
        required_accessible_names=(
            "프레임 16 / 61 · 0.25 s",
            "조작 이벤트: push · 0.25 s",
        ),
        screenshot_ms=1500,
    ),
    AuditCase(
        "replay_dense_events_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="replay_fixture,pause,accessibility_snapshot",
        accessibility=True,
        expect_experiment=True,
        fixture="dense_replay",
        required_accessible_names=(
            "조작 이벤트: damping ×10 · 0.29 s",
            "조작 이벤트: push · 0.80 s",
        ),
        expected_accessible_controls=19,
        require_unique_control_names=True,
        screenshot_ms=1600,
    ),
    AuditCase(
        "background_live_pause_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,record_backend,navigate_home,record_backend,"
            "record_backend,record_focus,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=(
            "실험 일시정지됨",
            "다른 화면을 보는 동안 물리는 멈춘 상태를 유지합니다. · LAB01 · 직접 조작",
            "실험으로 돌아가기",
            "종료하고 저장",
        ),
        required_descriptions=("실험으로 돌아가기", "종료하고 저장"),
        required_enabled_names=("실험으로 돌아가기", "종료하고 저장"),
        required_disabled_names=("다음 실험 시작",),
        required_in_window_names=("실험으로 돌아가기", "종료하고 저장"),
        forbidden_accessible_names=("건너뛰기",),
        required_description_texts=("먼저 위의 일시정지된 실험으로 돌아가거나 종료하고 저장하세요.",),
        expect_non_experiment=True,
        expected_transport_states=("running", "paused", "paused"),
        expected_pages=("experiment", "home", "home"),
        expected_active_trace=(True, True, True),
        stable_time_trace_pairs=((1, 2),),
        positive_time_trace_indices=(0, 1, 2),
        expected_focus_names=("홈",),
        action_interval_ms=700,
        screenshot_ms=4800,
    ),
    AuditCase(
        "background_live_return_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,navigate_explore,record_backend,return_experiment,"
            "record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        expect_experiment=True,
        required_accessible_names=("실험 진행률", "실험: 당기기", "재생"),
        forbidden_accessible_names=("실험으로 돌아가기", "종료하고 저장"),
        expected_transport_states=("paused", "paused"),
        expected_pages=("explore", "experiment"),
        expected_active_trace=(True, True),
        stable_time_trace_pairs=((0, 1),),
        positive_time_trace_indices=(0, 1),
        action_interval_ms=400,
        screenshot_ms=2800,
    ),
    AuditCase(
        "background_keyboard_return_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "navigate_home,record_focus,key_tab,key_tab,key_tab,key_tab,key_tab,"
            "record_focus,key_enter,record_backend,record_focus,accessibility_snapshot"
        ),
        accessibility=True,
        expect_experiment=True,
        required_accessible_names=("예측", "예측 후 시작", "실험 진행률"),
        forbidden_accessible_names=("실험으로 돌아가기", "종료하고 저장"),
        expected_focus_names=(
            "홈",
            "학습 경로",
            "탐색",
            "결과",
            "언어",
            "실험으로 돌아가기",
            "실험으로 돌아가기",
            "예측",
            "예측",
        ),
        expected_transport_states=("paused",),
        expected_pages=("experiment",),
        expected_active_trace=(True,),
        zero_time_trace_indices=(0,),
        action_interval_ms=300,
        screenshot_ms=4300,
    ),
    AuditCase(
        "background_prediction_pause_200pct_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions="navigate_home,record_backend,record_backend,accessibility_snapshot",
        accessibility=True,
        device_scale=2.0,
        expect_focus_ring=True,
        required_accessible_names=(
            "Experiment paused",
            "Physics stays paused while you view another screen. · LAB01 · Interactive",
            "Return to experiment",
            "End & save",
        ),
        required_descriptions=("Return to experiment", "End & save"),
        required_disabled_names=("Start next experiment",),
        required_description_texts=(
            "Return to or end and save the paused experiment above before starting another.",
        ),
        expect_non_experiment=True,
        expected_transport_states=("paused", "paused"),
        expected_pages=("home", "home"),
        expected_active_trace=(True, True),
        stable_time_trace_pairs=((0, 1),),
        zero_time_trace_indices=(0, 1),
        action_interval_ms=500,
        screenshot_ms=2300,
    ),
    AuditCase(
        "background_path_banner_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="navigate_path,record_backend,accessibility_snapshot",
        accessibility=True,
        expect_non_experiment=True,
        expect_focus_ring=True,
        required_accessible_names=(
            "실험 일시정지됨",
            "실험으로 돌아가기",
            "종료하고 저장",
            "학습 진행률",
        ),
        required_descriptions=("실험으로 돌아가기", "종료하고 저장"),
        required_disabled_names=("다음 실험 시작: LAB01 · 자동 데모",),
        required_description_texts=("먼저 위의 일시정지된 실험으로 돌아가거나 종료하고 저장하세요.",),
        expected_transport_states=("paused",),
        expected_pages=("path",),
        expected_active_trace=(True,),
        zero_time_trace_indices=(0,),
        action_interval_ms=500,
        screenshot_ms=1800,
    ),
    AuditCase(
        "background_explore_banner_1280_en",
        1280,
        720,
        "en",
        scenario="lab01.interactive-pull",
        actions="navigate_explore,record_backend,accessibility_snapshot",
        accessibility=True,
        expect_non_experiment=True,
        expect_focus_ring=True,
        required_accessible_names=(
            "Experiment paused",
            "Physics stays paused while you view another screen. · LAB01 · Interactive",
            "Return to experiment",
            "End & save",
            "Search scenarios",
            "Level filter",
            "Mode filter",
        ),
        required_descriptions=("Return to experiment", "End & save"),
        expected_scenario_starts=72,
        expected_disabled_scenario_starts=72,
        required_description_texts=(
            "Return to or end and save the paused experiment above before starting another.",
        ),
        expected_transport_states=("paused",),
        expected_pages=("explore",),
        expected_active_trace=(True,),
        zero_time_trace_indices=(0,),
        required_control_colors=(("Start: LAB01 · Auto demo", "#475569"),),
        required_control_color_pixels=((
            "Start: LAB01 · Auto demo", "#E2E8F0", 3_000,
        ),),
        required_control_border_colors=((
            "Start: LAB01 · Auto demo", "#64748B",
        ),),
        action_interval_ms=500,
        screenshot_ms=1800,
    ),
    AuditCase(
        "batch_running_explore_guard_1280_en",
        1280,
        720,
        "en",
        page="explore",
        actions="inject_batch_running,accessibility_snapshot",
        accessibility=True,
        expected_scenario_starts=72,
        expected_disabled_scenario_starts=72,
        required_description_texts=(
            "Cancel the course comparison above or wait for it to finish before starting another experiment.",
        ),
    ),
    AuditCase(
        "background_replay_pause_640_en",
        640,
        360,
        "en",
        page="results",
        actions=(
            "replay_fixture,navigate_results,record_backend,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        fixture="valid_replay",
        expect_focus_ring=True,
        required_accessible_names=(
            "Replay paused",
            "The recording stays on the current frame. · LAB01 · Interactive",
            "Return to replay",
            "Close replay",
        ),
        required_descriptions=("Return to replay", "Close replay"),
        required_disabled_names=("Replay recording: LAB01 · Interactive · Latest",),
        required_description_texts=(
            "Return to or close the paused replay above before opening another run.",
        ),
        expect_non_experiment=True,
        expected_transport_states=("paused", "paused"),
        expected_pages=("results", "results"),
        expected_active_trace=(True, True),
        stable_time_trace_pairs=((0, 1),),
        action_interval_ms=400,
        screenshot_ms=2600,
    ),
    AuditCase(
        "background_results_manage_guard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="navigate_results,open_result_manager,accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        expect_non_experiment=True,
        required_accessible_names=(
            "실험으로 돌아가기",
            "종료하고 저장",
            "같은 설정 재실행",
            "폴더 열기",
            "저장 실행을 복구 보관소로 이동",
            "닫기",
            "저장 결과를 재실행하거나 복구 보관소로 옮기려면 먼저 위의 일시정지된 실험으로 돌아가거나 종료하고 저장하세요.",
        ),
        required_enabled_names=("폴더 열기", "닫기"),
        required_disabled_names=("같은 설정 재실행", "저장 실행을 복구 보관소로 이동"),
        required_description_texts=(
            "저장 결과를 재실행하거나 복구 보관소로 옮기려면 먼저 위의 일시정지된 실험으로 돌아가거나 종료하고 저장하세요.",
        ),
        action_interval_ms=500,
        screenshot_ms=2300,
    ),
    AuditCase(
        "batch_running_results_manage_guard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,open_result_manager,accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=(
            "같은 설정 재실행",
            "폴더 열기",
            "저장 실행을 복구 보관소로 이동",
            "닫기",
            "전체 비교 중에는 저장 결과를 재실행할 수 없습니다. 폴더 열기와 무관한 저장 실행의 복구 보관소 이동은 계속 사용할 수 있습니다.",
        ),
        required_enabled_names=("폴더 열기", "저장 실행을 복구 보관소로 이동", "닫기"),
        required_disabled_names=("같은 설정 재실행",),
        required_description_texts=(
            "전체 비교 중에는 저장 결과를 재실행할 수 없습니다. 폴더 열기와 무관한 저장 실행의 복구 보관소 이동은 계속 사용할 수 있습니다.",
        ),
        action_interval_ms=500,
        screenshot_ms=2300,
    ),
    AuditCase(
        "batch_running_unrelated_delete_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions=(
            "inject_batch_running,open_result_manager,delete_managed_result,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=("비교 실행 취소", "첫 실험 시작"),
        required_disabled_names=("첫 실험 시작",),
        forbidden_accessible_names=("관리: LAB01 · 직접 조작 · 최신",),
        required_description_texts=(
            "위의 전체 비교를 취소하거나 완료될 때까지 기다린 뒤 새 실험을 시작하세요.",
        ),
        require_no_partially_clipped_controls=True,
        action_interval_ms=500,
        screenshot_ms=2800,
    ),
    AuditCase(
        "background_delete_backend_guard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "navigate_results,open_result_manager,probe_managed_result_backend_guard,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        fixture="valid_replay",
        expect_error=True,
        required_accessible_names=(
            "실험이 열려 있는 동안 저장 결과를 복구 보관소로 옮길 수 없습니다.",
            "권장 복구 행동: 실행 중인 실험으로 돌아가거나 종료하고 저장한 뒤 다른 실험을 시작하세요.",
            "세부정보 복사",
            "닫기",
        ),
        action_interval_ms=500,
        screenshot_ms=2800,
    ),
    AuditCase(
        "active_batch_backend_guard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="inject_batch_start_probe,start_all_compare,record_backend,accessibility_snapshot",
        accessibility=True,
        expect_error=True,
        required_accessible_names=(
            "다른 실험이 이미 실행 중입니다.",
            "권장 복구 행동: 실행 중인 실험으로 돌아가거나 종료하고 저장한 뒤 다른 실험을 시작하세요.",
            "세부정보 복사",
            "닫기",
        ),
        expected_transport_states=("paused",),
        expected_active_trace=(True,),
        expected_batch_probe_trace=(False,),
        zero_time_trace_indices=(0,),
        action_interval_ms=500,
        screenshot_ms=2300,
    ),
    AuditCase(
        "batch_running_replay_backend_guard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,replay_fixture,accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        expect_error=True,
        expect_non_experiment=True,
        required_accessible_names=(
            "전체 과정 비교가 이미 실행 중입니다.",
            "권장 복구 행동: 비교 실행 취소를 누르거나 다섯 세트가 끝날 때까지 기다리세요.",
            "세부정보 복사",
            "닫기",
        ),
        action_interval_ms=500,
        screenshot_ms=3200,
    ),
    AuditCase(
        "batch_running_rerun_backend_guard_640_ko",
        640,
        360,
        "ko",
        page="results",
        actions="inject_batch_running,rerun_fixture,accessibility_snapshot",
        accessibility=True,
        fixture="valid_replay",
        expect_error=True,
        expect_non_experiment=True,
        required_accessible_names=(
            "전체 과정 비교가 이미 실행 중입니다.",
            "권장 복구 행동: 비교 실행 취소를 누르거나 다섯 세트가 끝날 때까지 기다리세요.",
            "세부정보 복사",
            "닫기",
        ),
        action_interval_ms=500,
        screenshot_ms=3200,
    ),
    AuditCase(
        "completed_idle_batch_launch_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,finish_session,wait_worker,inject_batch_start_probe,"
            "start_all_compare,record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        required_accessible_names=("View saved results →",),
        forbidden_accessible_names=("Another experiment is already running.",),
        expected_transport_states=("completed",),
        expected_active_trace=(False,),
        expected_batch_probe_trace=(True,),
        action_interval_ms=500,
        screenshot_ms=6000,
    ),
    AuditCase(
        "background_end_and_save_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "navigate_home,record_backend,stop_active,wait_worker,record_backend,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        expect_non_experiment=True,
        expect_focus_ring=True,
        required_accessible_names=("다음 실험 시작",),
        required_enabled_names=("다음 실험 시작",),
        forbidden_accessible_names=("실험으로 돌아가기", "종료하고 저장"),
        expected_transport_states=("paused", "completed", "completed"),
        expected_pages=("home", "home", "home"),
        expected_active_trace=(True, False, False),
        zero_time_trace_indices=(0, 1, 2),
        action_interval_ms=1500,
        screenshot_ms=8500,
        auto_quit_grace_ms=3000,
    ),
    AuditCase(
        "background_saving_context_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="inject_live_completed,navigate_home,accessibility_snapshot",
        accessibility=True,
        expect_non_experiment=True,
        required_accessible_names=(
            "실험 증거 저장 중…",
            "새 실행 전에 기록과 리포트를 마무리하고 있습니다. · LAB01 · 직접 조작",
        ),
        forbidden_accessible_names=("실험으로 돌아가기", "종료하고 저장"),
        action_interval_ms=500,
        screenshot_ms=1900,
    ),
    AuditCase(
        "experiment_accessibility_640_ko",
        640,
        360,
        "ko",
        scenario="lab04.interactive-virtual-wall",
        actions="record_backend,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "지금 해볼 것: 조작하기 전에 무엇이 달라질지 한 문장으로 예측하세요.",
            "MuJoCo 실험 장면",
            "예측",
            "예측 확정",
            "예측 후 시작",
            "0.1초 진행",
            "다시 시작",
            "실험 진행률",
            "재생 속도",
            "Panda 팔",
            "벽 / 제약",
        ),
        required_descriptions=("MuJoCo 실험 장면", "예측", "실험 진행률"),
        required_disabled_names=("예측 확정", "예측 후 시작", "0.1초 진행", "다시 시작"),
        required_description_texts=("0.00초부터 시작", "접촉 힘"),
        required_nonfocusable_names=("실험 진행률",),
        forbidden_accessible_names=("기록 재생 타임라인", "목표 X", "가상 벽 X"),
        required_scene_tokens=("current", "target", "wall"),
        required_now_prompt_fragments=("예측", "조작하기 전에"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        expected_transport_states=("paused",),
        zero_time_trace_indices=(0,),
    ),
    AuditCase(
        "experiment_primary_prediction_1280_en",
        1280,
        720,
        "en",
        scenario="lab01.interactive-pull",
        actions="type_prediction,record_backend,accessibility_snapshot",
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("Set prediction",),
        required_in_window_names=("Set prediction",),
        maximum_prediction_horizontal_overflow=1.0,
        maximum_prediction_vertical_overflow=1.0,
        minimum_prediction_line_count=1,
        maximum_prediction_line_count=1,
        expected_prediction_vertical_scrollbar=False,
        screenshot_ms=2200,
    ),
    AuditCase(
        "experiment_prediction_wrap_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="type_prediction,record_backend,accessibility_snapshot",
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("예측 확정",),
        required_in_window_names=("예측 확정",),
        maximum_prediction_horizontal_overflow=1.0,
        maximum_prediction_vertical_overflow=1.0,
        minimum_prediction_line_count=2,
        maximum_prediction_line_count=3,
        expected_prediction_vertical_scrollbar=False,
        screenshot_ms=2200,
    ),
    AuditCase(
        "experiment_prediction_limit_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "type_prediction_limit,prediction_cursor_end,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("Set prediction",),
        required_in_window_names=("Set prediction",),
        maximum_prediction_horizontal_overflow=1.0,
        minimum_prediction_vertical_overflow=80.0,
        minimum_prediction_line_count=8,
        expected_prediction_vertical_scrollbar=True,
        minimum_prediction_scroll_position=80.0,
        expected_prediction_input_length=240,
        screenshot_ms=2400,
    ),
    AuditCase(
        "experiment_prediction_limit_1280_en",
        1280,
        720,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "type_prediction_limit,prediction_cursor_end,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("Set prediction",),
        required_in_window_names=("Set prediction",),
        maximum_prediction_horizontal_overflow=1.0,
        minimum_prediction_vertical_overflow=30.0,
        minimum_prediction_line_count=4,
        expected_prediction_vertical_scrollbar=True,
        minimum_prediction_scroll_position=30.0,
        expected_prediction_input_length=240,
        screenshot_ms=2400,
    ),
    AuditCase(
        "experiment_prediction_limit_start_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "type_prediction_limit_ko,prediction_cursor_end,record_backend,"
            "prediction_cursor_start,record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("예측 확정",),
        required_in_window_names=("예측 확정",),
        maximum_prediction_horizontal_overflow=1.0,
        minimum_prediction_vertical_overflow=80.0,
        minimum_prediction_line_count=8,
        expected_prediction_vertical_scrollbar=True,
        maximum_prediction_scroll_position=1.0,
        minimum_prediction_peak_scroll_position=180.0,
        expected_prediction_input_length=240,
        device_scale=2.0,
        screenshot_ms=2600,
    ),
    AuditCase(
        "experiment_prediction_limit_keyboard_save_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "type_prediction_limit,prediction_cursor_end,key_tab,"
            "key_enter,record_backend,accessibility_snapshot,finish_session"
        ),
        accessibility=True,
        expected_focus_names=("Predict", "Set prediction", "Experiment: Push"),
        expected_evidence_trace=((True, False, False, 2),),
        expected_saved_prediction_length=240,
        required_interaction_event_names=("prediction",),
        expected_transport_states=("running",),
        screenshot_ms=4200,
    ),
    AuditCase(
        "experiment_prediction_limit_keyboard_save_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "type_prediction_limit_ko,prediction_cursor_end,key_tab,key_enter,"
            "record_backend,accessibility_snapshot,finish_session"
        ),
        accessibility=True,
        expected_focus_names=("예측", "예측 확정", "실험: 밀기"),
        expected_evidence_trace=((True, False, False, 2),),
        expected_saved_prediction_length=240,
        required_interaction_event_names=("prediction",),
        expected_transport_states=("running",),
        device_scale=2.0,
        screenshot_ms=4400,
    ),
    AuditCase(
        "experiment_primary_manipulation_1280_en",
        1280,
        720,
        "en",
        scenario="lab01.interactive-pull",
        actions="save_prediction,pause,accessibility_snapshot",
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("Experiment: Push",),
        required_in_window_names=("Experiment: Push",),
        screenshot_ms=2600,
    ),
    AuditCase(
        "experiment_primary_prediction_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="type_prediction,record_backend,accessibility_snapshot",
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("예측 확정",),
        required_in_window_names=("예측 확정",),
        maximum_prediction_horizontal_overflow=1.0,
        maximum_prediction_vertical_overflow=1.0,
        minimum_prediction_line_count=2,
        maximum_prediction_line_count=3,
        expected_prediction_vertical_scrollbar=False,
        device_scale=2.0,
        screenshot_ms=2400,
    ),
    AuditCase(
        "experiment_primary_manipulation_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="save_prediction,pause,accessibility_snapshot",
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("실험: 밀기",),
        required_in_window_names=("실험: 밀기",),
        screenshot_ms=2600,
    ),
    AuditCase(
        "experiment_primary_observation_ready_1280_en",
        1280,
        720,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,pause,type_observation,"
            "select_outcome_matched,accessibility_snapshot"
        ),
        accessibility=True,
        maximum_primary_actions=1,
        required_primary_names=("Save observation",),
        required_in_window_names=("Save observation",),
        screenshot_ms=3400,
    ),
    AuditCase(
        "experiment_observation_limit_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,pause,type_observation_limit,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        required_accessible_names=("Observe", "Prediction outcome", "Save observation"),
        required_in_window_names=("Observe", "Prediction outcome", "Save observation"),
        maximum_observation_horizontal_overflow=1.0,
        minimum_observation_vertical_overflow=150.0,
        minimum_observation_line_count=10,
        expected_observation_vertical_scrollbar=True,
        minimum_observation_scroll_position=180.0,
        expected_observation_input_length=300,
        screenshot_ms=3600,
    ),
    AuditCase(
        "experiment_observation_wrap_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,pause,type_observation,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        maximum_observation_horizontal_overflow=1.0,
        maximum_observation_vertical_overflow=1.0,
        minimum_observation_line_count=1,
        maximum_observation_line_count=3,
        expected_observation_vertical_scrollbar=False,
        expected_observation_input_length=42,
        screenshot_ms=3000,
    ),
    AuditCase(
        "experiment_observation_limit_1280_en",
        1280,
        720,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,pause,type_observation_limit,"
            "observation_cursor_end,record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        maximum_observation_horizontal_overflow=1.0,
        minimum_observation_vertical_overflow=30.0,
        minimum_observation_line_count=4,
        expected_observation_vertical_scrollbar=True,
        minimum_observation_scroll_position=30.0,
        expected_observation_input_length=300,
        screenshot_ms=3600,
    ),
    AuditCase(
        "experiment_observation_limit_start_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,pause,type_observation_limit_ko,"
            "observation_cursor_end,record_backend,observation_cursor_start,"
            "record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        maximum_observation_horizontal_overflow=1.0,
        minimum_observation_vertical_overflow=180.0,
        minimum_observation_line_count=12,
        expected_observation_vertical_scrollbar=True,
        maximum_observation_scroll_position=1.0,
        minimum_observation_peak_scroll_position=180.0,
        expected_observation_input_length=300,
        device_scale=2.0,
        screenshot_ms=4000,
    ),
    AuditCase(
        "experiment_observation_limit_keyboard_save_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,pause,type_observation_limit,"
            "observation_cursor_end,key_tab,key_down,key_tab,key_enter,"
            "record_backend,accessibility_snapshot,finish_session"
        ),
        accessibility=True,
        expected_focus_names=(
            "Observe",
            "Prediction outcome",
            "Prediction outcome",
            "Save observation",
            "Play",
        ),
        required_accessible_names=("✓ Evidence saved", "Core experiment controls"),
        required_contained_pairs=(("✓ Evidence saved", "Core experiment controls"),),
        expected_evidence_trace=((True, True, True, 4),),
        expected_saved_observation_length=300,
        required_interaction_event_names=("prediction", "push", "observation"),
        expected_transport_states=("paused",),
        screenshot_ms=5200,
    ),
    AuditCase(
        "experiment_observation_limit_keyboard_save_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,pause,type_observation_limit_ko,"
            "observation_cursor_end,key_tab,key_down,key_tab,key_enter,"
            "record_backend,accessibility_snapshot,finish_session"
        ),
        accessibility=True,
        expected_focus_names=(
            "관찰",
            "예측 결과",
            "예측 결과",
            "관찰 저장",
            "재생",
        ),
        required_accessible_names=("✓ 증거 저장됨", "핵심 실험 제어"),
        required_contained_pairs=(("✓ 증거 저장됨", "핵심 실험 제어"),),
        expected_evidence_trace=((True, True, True, 4),),
        expected_saved_observation_length=300,
        required_interaction_event_names=("prediction", "push", "observation"),
        expected_transport_states=("paused",),
        device_scale=2.0,
        screenshot_ms=5400,
    ),
    AuditCase(
        "experiment_observation_save_running_focus_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,type_observation,key_tab,key_down,key_tab,key_enter,"
            "record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        expected_focus_names=(
            "Observe",
            "Prediction outcome",
            "Prediction outcome",
            "Save observation",
            "Pause",
        ),
        expected_evidence_trace=((True, True, True, 4),),
        expected_transport_states=("running",),
        required_accessible_names=(
            "✓ Evidence saved",
            "Core experiment controls",
            "Pause",
        ),
        required_contained_pairs=(("✓ Evidence saved", "Core experiment controls"),),
        maximum_primary_actions=1,
        required_primary_names=("Pause",),
        screenshot_ms=3600,
    ),
    AuditCase(
        "evidence_prediction_boundary_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="focus_scene,record_focus,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("예측", "MuJoCo 실험 장면"),
        # Qt exposes scrollable future controls to assistive technology even
        # while the compact panel clips them. Bound the control under test,
        # rather than treating every scroll descendant as visually present.
        required_in_window_names=("예측",),
        required_control_border_colors=(("예측", "#64748B"),),
        expected_focus_names=("MuJoCo 실험 장면",),
    ),
    AuditCase(
        "evidence_observation_boundary_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions="save_prediction,push,focus_scene,record_focus,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("Observe", "Prediction outcome"),
        required_in_window_names=("Observe", "Prediction outcome"),
        required_control_border_colors=(
            ("Observe", "#64748B"),
            ("Prediction outcome", "#64748B"),
            ("Advance 0.1 s", "#64748B"),
            ("Restart", "#64748B"),
        ),
        expected_focus_names=("MuJoCo experiment scene",),
        action_interval_ms=350,
        screenshot_ms=2200,
    ),
    AuditCase(
        "advanced_settings_checkbox_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,focus_advanced_toggle,record_focus,key_space,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        required_accessible_names=("Advanced settings",),
        required_descriptions=("Advanced settings",),
        required_in_window_names=("Advanced settings",),
        expected_focus_names=("Advanced settings", "Advanced settings"),
        required_indicator_colors=(("Advanced settings", "#2563EB", 200),),
        required_checked_names=("Advanced settings",),
        required_single_line_control_names=("Advanced settings",),
        action_interval_ms=350,
        screenshot_ms=2100,
    ),
    AuditCase(
        "camera_help_hover_1280_en",
        1280,
        720,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="hover_reset_camera,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("MuJoCo experiment scene", "Reset camera"),
        required_descriptions=("MuJoCo experiment scene", "Reset camera"),
        required_description_texts=(
            "drag to orbit",
            "right-drag to pan",
            "wheel to zoom",
            "Returns to the default view",
        ),
        action_interval_ms=800,
        screenshot_ms=2400,
    ),
    AuditCase(
        "camera_help_focus_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="save_prediction,focus_reset_camera,record_focus,accessibility_snapshot",
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=("MuJoCo 실험 장면", "카메라 초기화"),
        required_descriptions=("MuJoCo 실험 장면", "카메라 초기화"),
        required_description_texts=(
            "드래그 회전",
            "오른쪽 드래그 이동",
            "휠 확대/축소",
            "기본 시점으로 되돌립니다",
        ),
        required_in_window_names=("카메라 초기화",),
        expected_focus_names=("카메라 초기화",),
        action_interval_ms=600,
        screenshot_ms=2800,
    ),
    AuditCase(
        "camera_keyboard_focus_640_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,focus_scene,record_focus,key_left,key_shift_up,"
            "key_plus,key_zero,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=(
            "MuJoCo experiment scene",
            "Scene markers: Current, Target, Force. "
            "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
        ),
        required_descriptions=("MuJoCo experiment scene",),
        required_description_texts=("Arrow keys", "Shift+Arrow", "+/-", "0 resets"),
        required_in_window_names=(
            "MuJoCo experiment scene",
            "Scene markers: Current, Target, Force. "
            "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
        ),
        expected_focus_names=("MuJoCo experiment scene",) * 5,
        action_interval_ms=500,
        screenshot_ms=5200,
    ),
    AuditCase(
        "camera_keyboard_focus_1280_wall_en",
        1280,
        720,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="focus_scene,record_focus,accessibility_snapshot",
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=(
            "Scene markers: Current, Target, Force, Wall / constraint. "
            "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
        ),
        required_in_window_names=(
            "Scene markers: Current, Target, Force, Wall / constraint. "
            "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
        ),
        expected_focus_names=("MuJoCo experiment scene",),
        required_scene_tokens=("current", "target", "wall"),
        action_interval_ms=500,
        screenshot_ms=2300,
    ),
    AuditCase(
        "camera_keyboard_focus_640_wall_en",
        640,
        360,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="focus_scene,record_focus,accessibility_snapshot",
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=(
            "Scene markers: Current, Target, Force, Wall / constraint. "
            "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
        ),
        required_in_window_names=(
            "Scene markers: Current, Target, Force, Wall / constraint. "
            "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
        ),
        expected_focus_names=("MuJoCo experiment scene",),
        required_scene_tokens=("current", "target", "wall"),
        action_interval_ms=500,
        screenshot_ms=2300,
    ),
    AuditCase(
        "safe_lab03_tracking_640_ko",
        640,
        360,
        "ko",
        scenario="lab03.interactive-tracking",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("예측", "MuJoCo 실험 장면"),
        required_scene_tokens=("current", "target"),
    ),
    AuditCase(
        "safe_lab03_arm_640_ko",
        640,
        360,
        "ko",
        scenario="lab03.interactive-2dof",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("관절 1 · 2", "작업공간"),
        required_scene_tokens=("current", "target", "workspace"),
    ),
    AuditCase(
        "safe_lab03_arm_1280_en",
        1280,
        720,
        "en",
        scenario="lab03.interactive-2dof",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Joints 1 · 2",
            "Workspace",
            "Current hand",
            "Target hand",
        ),
        required_in_window_names=("Current hand", "Target hand"),
        required_non_overlapping_pairs=(("Current hand", "Target hand"),),
        required_scene_tokens=("current", "target", "workspace"),
    ),
    AuditCase(
        "safe_lab03_arm_1920_ko",
        1920,
        1080,
        "ko",
        scenario="lab03.interactive-2dof",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("관절 1 · 2", "작업공간", "현재 손끝", "목표 손끝"),
        required_in_window_names=("현재 손끝", "목표 손끝"),
        required_scene_tokens=("current", "target", "workspace"),
        minimum_scene_token_pixels=(
            ("current", 1_000),
            ("target", 1_000),
            ("workspace", 2_000),
        ),
    ),
    AuditCase(
        "safe_lab04_cartesian_640_en",
        640,
        360,
        "en",
        scenario="lab04.interactive-cartesian-reach",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("Panda arm",),
        required_scene_tokens=("current", "target"),
    ),
    AuditCase(
        "safe_lab04_wall_200pct_en",
        640,
        360,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="accessibility_snapshot",
        accessibility=True,
        device_scale=2.0,
        required_accessible_names=("Panda arm", "Wall / constraint"),
        required_scene_tokens=("current", "target", "wall"),
    ),
    AuditCase(
        "safe_lab04_wall_1280_ko",
        1280,
        720,
        "ko",
        scenario="lab04.interactive-virtual-wall",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("Panda 팔", "벽 / 제약", "현재 손끝", "목표 손끝"),
        required_in_window_names=("현재 손끝", "목표 손끝"),
        required_non_overlapping_pairs=(("현재 손끝", "목표 손끝"),),
        required_scene_tokens=("current", "target", "wall"),
    ),
    AuditCase(
        "safe_lab04_wall_crossed_target_1280_en",
        1280,
        720,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions=(
            "save_prediction,control_target_x=0.75,control_wall_x=0.50,pause,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        required_accessible_names=(
            "Current hand",
            "Target hand",
            "Wall / constraint",
            "↗ Moving",
        ),
        required_in_window_names=("Current hand", "Target hand"),
        required_non_overlapping_pairs=(
            ("Current hand", "Target hand"),
            ("Target hand", "↗ Moving"),
        ),
        required_scene_tokens=("current", "target", "wall"),
        screenshot_ms=3000,
    ),
    AuditCase(
        "safe_lab04_wall_1920_en",
        1920,
        1080,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Panda arm",
            "Wall / constraint",
            "Current hand",
            "Target hand",
        ),
        required_in_window_names=("Current hand", "Target hand"),
        required_scene_tokens=("current", "target", "wall"),
        minimum_scene_token_pixels=(
            ("current", 1_000),
            ("target", 1_000),
            ("wall", 7_000),
        ),
    ),
    AuditCase(
        "experiment_prompt_640_en",
        640,
        360,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="record_backend,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Try this now: Write one sentence about what will change before using a control.",
        ),
        required_now_prompt_fragments=("one sentence", "before using a control"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        expected_transport_states=("paused",),
        zero_time_trace_indices=(0,),
    ),
    AuditCase(
        "prediction_context_language_switch_640",
        640,
        360,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="language_ko,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("예측", "예측 확정"),
        required_descriptions=("예측",),
        required_description_texts=("접촉 힘",),
        forbidden_accessible_names=("Make a prediction",),
    ),
    AuditCase(
        "experiment_prompt_longest_640_en",
        640,
        360,
        "en",
        scenario="lab04.interactive-joint-hold",
        actions="save_prediction,record_backend,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Try this now: Target X +, then Joint target offset.",
            "Experiment: Target X +",
            "Joint target offset",
        ),
        required_now_prompt_fragments=("Target X +", "Joint target offset", "then"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
    ),
    AuditCase(
        "experiment_evidence_keyboard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "record_backend,record_focus,type_prediction,key_tab,"
            "key_enter,record_backend,key_enter,record_backend,key_backtab,key_backtab,"
            "type_observation,key_tab,key_down,key_tab,key_enter,record_focus,record_backend,"
            "accessibility_snapshot,finish_session"
        ),
        accessibility=True,
        required_accessible_names=("✓ 증거 저장됨", "카메라 초기화"),
        expected_evidence_trace=(
            (False, False, False, 1),
            (True, False, False, 2),
            (True, True, False, 3),
            (True, True, True, 4),
        ),
        require_evidence_artifact=True,
        required_report_texts=("Mission Evidence", "Ready for review"),
        expected_transport_states=("paused", "running", "running", "running"),
        zero_time_trace_indices=(0,),
        positive_time_trace_indices=(1, 2, 3),
        action_interval_ms=250,
        screenshot_ms=7200,
    ),
    AuditCase(
        "experiment_evidence_reset_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "record_backend,save_prediction,record_backend,push,record_backend,"
            "reset_experiment,record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        required_accessible_names=("예측", "예측 후 시작"),
        required_disabled_names=("예측 후 시작",),
        expected_evidence_trace=(
            (False, False, False, 1),
            (True, False, False, 2),
            (True, True, False, 3),
            (False, False, False, 1),
        ),
        expected_transport_states=("paused", "running", "running", "paused"),
        zero_time_trace_indices=(0, 3),
        positive_time_trace_indices=(1, 2),
        action_interval_ms=400,
        screenshot_ms=4200,
    ),
    AuditCase(
        "completed_evidence_retry_keyboard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,remember_session,finish_session,wait_worker,record_backend,"
            "focus_experiment,record_focus,press_enter,wait_restart,record_focus,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=("예측", "예측 확정", "예측 후 시작", "실험 진행률"),
        required_disabled_names=("예측 확정", "예측 후 시작", "0.1초 진행", "다시 시작"),
        required_in_window_names=("예측", "예측 확정", "예측 후 시작"),
        expected_focus_names=("다시 시작", "예측"),
        expected_transport_states=("completed", "paused"),
        expected_evidence_trace=((True, False, False, 2), (False, False, False, 1)),
        zero_time_trace_indices=(1,),
        require_no_partially_clipped_controls=True,
        action_interval_ms=500,
        screenshot_ms=8000,
        auto_quit_grace_ms=5000,
    ),
    AuditCase(
        "experiment_keyboard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="save_prediction,push,key_space,key_right",
    ),
    AuditCase(
        "live_progress_keyboard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="save_prediction,pause,focus_experiment,key_backtab,record_focus,accessibility_snapshot",
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=("실험 진행률",),
        required_descriptions=("실험 진행률",),
        required_nonfocusable_names=("실험 진행률",),
        forbidden_accessible_names=("기록 재생 타임라인",),
        expected_focus_names=("고급 설정", "고급 설정"),
        action_interval_ms=400,
        screenshot_ms=2200,
    ),
    AuditCase(
        "speed_restart_sync_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,remember_session,speed_0_5,record_backend,finish_session,"
            "wait_worker,record_backend,record_backend,pause,wait_restart,save_prediction,"
            "record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        required_accessible_names=("재생 속도",),
        required_descriptions=("재생 속도",),
        required_description_texts=("현재 0.5×",),
        expected_speed_trace=(0.5, 0.5, 0.5, 0.5),
        expected_transport_states=("running", "completed", "completed", "running"),
        expected_cleanup_trace=(False, True, True, True),
        action_interval_ms=800,
        screenshot_ms=14_000,
        auto_quit_grace_ms=8_000,
    ),
    AuditCase(
        "speed_keyboard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,focus_experiment,key_tab,key_tab,key_tab,record_focus,key_up,record_focus,"
            "record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=("재생 속도",),
        required_descriptions=("재생 속도",),
        required_description_texts=("현재 0.5×", "위/아래 화살표"),
        expected_focus_names=(
            "0.1초 진행",
            "다시 시작",
            "재생 속도",
            "재생 속도",
            "재생 속도",
            "재생 속도",
        ),
        expected_speed_trace=(0.5,),
        expected_transport_states=("running",),
        action_interval_ms=400,
        screenshot_ms=3800,
    ),
    AuditCase(
        "speed_replay_sync_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,remember_session,speed_0_5,record_backend,finish_session,record_backend,record_backend,"
            "wait_worker,replay_fixture,record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        fixture="valid_replay",
        required_accessible_names=("재생 속도", "기록 재생 타임라인"),
        required_descriptions=("재생 속도", "기록 재생 타임라인"),
        required_description_texts=("현재 0.5×",),
        expected_speed_trace=(0.5, 0.5, 0.5, 0.5),
        expected_transport_states=("running", "completed", "completed", "replaying"),
        expected_cleanup_trace=(False, True, True, True),
        action_interval_ms=1000,
        screenshot_ms=14_000,
    ),
    AuditCase(
        "duplicate_replay_guard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,remember_session,record_backend,replay_fixture,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        expect_error=True,
        fixture="valid_replay",
        required_accessible_names=(
            "다른 실험이 이미 실행 중입니다.",
            "권장 복구 행동: 실행 중인 실험으로 돌아가거나 종료하고 저장한 뒤 다른 실험을 시작하세요.",
            "세부정보 복사",
            "닫기",
        ),
        required_descriptions=("세부정보 복사",),
        expected_speed_trace=(1.0, 1.0),
        expected_transport_states=("running", "running"),
        expected_cleanup_trace=(False, False),
        expect_no_session_replacement=True,
        action_interval_ms=500,
        screenshot_ms=3200,
    ),
    AuditCase(
        "duplicate_scenario_guard_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,remember_session,record_backend,start_next,record_backend,"
            "accessibility_snapshot"
        ),
        accessibility=True,
        expect_error=True,
        required_accessible_names=(
            "다른 실험이 이미 실행 중입니다.",
            "권장 복구 행동: 실행 중인 실험으로 돌아가거나 종료하고 저장한 뒤 다른 실험을 시작하세요.",
            "세부정보 복사",
            "닫기",
        ),
        required_descriptions=("세부정보 복사",),
        expected_speed_trace=(1.0, 1.0),
        expected_transport_states=("running", "running"),
        expected_cleanup_trace=(False, False),
        expect_no_session_replacement=True,
        action_interval_ms=500,
        screenshot_ms=3200,
    ),
    AuditCase(
        "repeated_restart_cleanup_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,remember_session,finish_session,wait_worker,record_backend,"
            "pause,wait_restart,save_prediction,record_backend,remember_session,"
            "finish_session,wait_worker,record_backend,pause,wait_restart,save_prediction,"
            "record_backend,remember_session,finish_session,wait_worker,record_backend,"
            "pause,wait_restart,save_prediction,record_backend"
        ),
        expected_speed_trace=(1.0,) * 6,
        expected_transport_states=(
            "completed", "running", "completed", "running", "completed", "running"
        ),
        expected_cleanup_trace=(True,) * 6,
        maximum_rss_growth_kb=65_536,
        rss_ignore_initial_samples=1,
        action_interval_ms=800,
        screenshot_ms=24_000,
        auto_quit_grace_ms=12_000,
    ),
    AuditCase(
        "panel_focus_scroll_640_ko",
        640,
        360,
        "ko",
        scenario="lab04.interactive-virtual-wall",
        actions=(
            "save_prediction,pause,focus_experiment,key_backtab,key_backtab,key_backtab,"
            "key_backtab,key_backtab,key_backtab,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        expected_focus_names=(
            "고급 설정",
            "카메라 초기화",
            "벽 후퇴 게인",
            "벽 감쇠",
            "벽 강성",
            "가상 벽 X",
        ),
        action_interval_ms=300,
        screenshot_ms=4400,
    ),
    AuditCase(
        "experiment_focus_shortcuts_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="record_backend,record_focus,key_space,record_focus,key_right,record_focus,record_backend",
        expect_focus_ring=True,
        expected_focus_names=("예측", "예측", "예측", "예측", "예측"),
        expected_transport_states=("paused", "paused"),
        zero_time_trace_indices=(0, 1),
        action_interval_ms=300,
        screenshot_ms=2100,
    ),
    AuditCase(
        "experiment_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "MuJoCo 실험 장면",
            "예측",
            "예측 확정",
            "예측 후 시작",
            "실험 진행률",
            "재생 속도",
        ),
        required_descriptions=("MuJoCo 실험 장면", "예측", "실험 진행률"),
        required_disabled_names=("예측 확정", "예측 후 시작"),
        required_nonfocusable_names=("실험 진행률",),
        forbidden_accessible_names=("기록 재생 타임라인", "질량"),
        required_control_colors=(("예측 확정", "#475569"),),
        required_control_color_pixels=(("예측 확정", "#E2E8F0", 10_000),),
        required_control_border_colors=(("예측 확정", "#64748B"),),
        device_scale=2.0,
    ),
    AuditCase(
        "experiment_completed_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="save_prediction,inject_live_completed,record_backend,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "다시 시작한 뒤 예측 → 한 가지 조작 → 관찰 저장을 완료하세요.",
            "저장 결과 보기 →",
            "다시 시작",
            "0.1초 진행",
        ),
        required_descriptions=("저장 결과 보기 →", "다시 시작"),
        required_description_texts=("다시 시작한 뒤 예측",),
        required_disabled_names=("0.1초 진행",),
        required_in_window_names=(
            "다시 시작한 뒤 예측 → 한 가지 조작 → 관찰 저장을 완료하세요.",
            "저장 결과 보기 →",
            "다시 시작",
        ),
        required_now_prompt_fragments=("다시 시작", "예측", "관찰 저장"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        maximum_primary_actions=1,
        required_primary_names=("다시 시작",),
        forbidden_accessible_names=("← 홈",),
        require_unique_control_names=True,
        device_scale=2.0,
    ),
    AuditCase(
        "experiment_evidence_complete_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "save_prediction,push,save_observation_matched,inject_live_completed,"
            "record_focus,record_backend,accessibility_snapshot"
        ),
        accessibility=True,
        expected_focus_names=("저장 결과 보기 →",),
        required_accessible_names=(
            "✓ 증거 저장됨",
            "저장 결과 보기 →",
            "다시 시작",
            "0.1초 진행",
        ),
        required_descriptions=("저장 결과 보기 →",),
        required_disabled_names=("0.1초 진행",),
        required_in_window_names=("✓ 증거 저장됨", "저장 결과 보기 →", "다시 시작"),
        required_contained_pairs=(("✓ 증거 저장됨", "핵심 실험 제어"),),
        required_now_prompt_fragments=("복습", "결과", "재생"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        maximum_primary_actions=1,
        required_primary_names=("저장 결과 보기 →",),
        forbidden_accessible_names=("← 홈",),
        require_unique_control_names=True,
        device_scale=2.0,
    ),
    AuditCase(
        "experiment_completed_200pct_en",
        640,
        360,
        "en",
        scenario="lab01.interactive-pull",
        actions="save_prediction,inject_live_completed,record_backend,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Restart, then complete prediction → one control → observation.",
            "View saved results →",
            "Restart",
            "Advance 0.1 s",
        ),
        required_descriptions=("View saved results →", "Restart"),
        required_description_texts=("complete prediction → one control",),
        required_disabled_names=("Advance 0.1 s",),
        required_in_window_names=(
            "Restart, then complete prediction → one control → observation.",
            "View saved results →",
            "Restart",
        ),
        required_now_prompt_fragments=("Restart", "prediction", "observation"),
        maximum_now_prompt_lines=2,
        require_untruncated_now_prompt=True,
        maximum_primary_actions=1,
        required_primary_names=("Restart",),
        forbidden_accessible_names=("← Home",),
        require_unique_control_names=True,
        device_scale=2.0,
    ),
    AuditCase(
        "keyboard_start_640_ko",
        640,
        360,
        "ko",
        actions=(
            "key_tab,key_tab,key_tab,key_tab,key_tab,key_tab,key_tab,"
            "key_backtab,key_tab,key_enter"
        ),
        expect_experiment=True,
        action_interval_ms=80,
        expected_focus_names=(
            "홈",
            "학습 경로",
            "탐색",
            "결과",
            "언어",
            "건너뛰기",
            "다음 실험 시작",
            "건너뛰기",
            "다음 실험 시작",
            "일시정지",
        ),
    ),
    AuditCase(
        "experiment_1280_en",
        1280,
        720,
        "en",
        scenario="lab01.interactive-pull",
        actions="save_prediction,push,pause,step",
    ),
    AuditCase(
        "experiment_1920_ko",
        1920,
        1080,
        "ko",
        scenario="lab01.interactive-pull",
        actions="save_prediction,push,pause,step",
        required_scene_tokens=("current", "target", "force"),
        minimum_scene_token_pixels=(("current", 8_000), ("target", 320), ("force", 300)),
    ),
    AuditCase(
        "error_recovery_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="invalid_beta_action",
        expect_error=True,
    ),
    AuditCase(
        "error_recovery_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="invalid_beta_action,accessibility_snapshot",
        expect_error=True,
        accessibility=True,
        required_accessible_names=(
            "요청을 처리하지 못했습니다.",
            "세부정보 복사",
            "닫기",
            "기술 세부정보 보기",
        ),
        required_descriptions=("세부정보 복사",),
        forbidden_accessible_names=(
            "요청을 처리하지 못했습니다. 기술 세부정보: KeyError: "
            "'Unsupported Lab01 action: invalid_beta_action'",
        ),
        device_scale=2.0,
        required_control_border_colors=(("세부정보 복사", "#64748B"),),
        required_role_border_colors=((
            "Dialog",
            "MCLab을 계속 실행할 수 없습니다",
            "#64748B",
            1_000,
        ),),
        required_indicator_colors=(("기술 세부정보 보기", "#64748B", 300),),
        required_unchecked_names=("기술 세부정보 보기",),
        required_single_line_control_names=("기술 세부정보 보기",),
    ),
    AuditCase(
        "error_details_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions="invalid_beta_action,key_tab,key_space,accessibility_snapshot",
        expect_error=True,
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=(
            "요청을 처리하지 못했습니다.",
            "세부정보 복사",
            "닫기",
            "기술 세부정보 보기",
        ),
        required_descriptions=("세부정보 복사",),
        device_scale=2.0,
        expected_focus_names=("기술 세부정보 보기", "기술 세부정보 보기"),
        required_indicator_colors=(("기술 세부정보 보기", "#2563EB", 1200),),
        required_checked_names=("기술 세부정보 보기",),
        action_interval_ms=500,
        screenshot_ms=2200,
    ),
    AuditCase(
        "error_details_toggle_back_200pct_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "invalid_beta_action,key_tab,key_space,key_space,accessibility_snapshot"
        ),
        expect_error=True,
        accessibility=True,
        expect_focus_ring=True,
        required_accessible_names=("기술 세부정보 보기",),
        required_descriptions=("기술 세부정보 보기",),
        expected_focus_names=(
            "기술 세부정보 보기",
            "기술 세부정보 보기",
            "기술 세부정보 보기",
        ),
        required_indicator_colors=(("기술 세부정보 보기", "#64748B", 300),),
        required_unchecked_names=("기술 세부정보 보기",),
        device_scale=2.0,
        action_interval_ms=450,
        screenshot_ms=2600,
    ),
    AuditCase(
        "error_focus_return_640_ko",
        640,
        360,
        "ko",
        scenario="lab01.interactive-pull",
        actions=(
            "invalid_beta_action,record_focus,key_tab,key_tab,key_tab,key_tab,"
            "key_escape,record_focus"
        ),
        expect_focus_ring=True,
        expected_focus_names=(
            "닫기",
            "기술 세부정보 보기",
            "세부정보 복사",
            "닫기",
            "기술 세부정보 보기",
            "예측",
            "예측",
        ),
        action_interval_ms=350,
        screenshot_ms=3000,
    ),
    AuditCase(
        "experiment_control_precision_640_en",
        640,
        360,
        "en",
        scenario="lab04.interactive-virtual-wall",
        actions="save_prediction,pause,key_tab,key_right,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("Target X: 0.615 m",),
        required_in_window_names=("Target X: 0.615 m",),
        required_text_metrics=(("Target X: 0.615 m", "#1D4ED8", 17),),
        screenshot_ms=3000,
    ),
    AuditCase(
        "experiment_control_precision_1280_ko",
        1280,
        720,
        "ko",
        scenario="lab04.interactive-virtual-wall",
        actions="save_prediction,pause,key_tab,key_right,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=("목표 X: 0.615 m",),
        required_in_window_names=("목표 X: 0.615 m",),
        required_text_metrics=(("목표 X: 0.615 m", "#1D4ED8", 17),),
        screenshot_ms=3000,
    ),
    AuditCase(
        "experiment_core_controls_visible_1280_en",
        1280,
        720,
        "en",
        scenario="lab02.interactive-disturbance",
        actions="save_prediction,push,pause,accessibility_snapshot",
        accessibility=True,
        required_accessible_names=(
            "Observe",
            "Prediction outcome",
            "Core experiment controls",
            "Position",
            "Proportional gain Kp",
            "Integral gain Ki",
            "Derivative gain Kd",
            "Force limit",
            "Position: 0.00 m",
            "Proportional gain Kp: 60",
            "Integral gain Ki: 2.0",
            "Derivative gain Kd: 12.0",
            "Force limit: 80 N",
        ),
        required_in_window_names=(
            "Observe",
            "Prediction outcome",
            "Position: 0.00 m",
            "Proportional gain Kp: 60",
            "Integral gain Ki: 2.0",
            "Derivative gain Kd: 12.0",
            "Force limit: 80 N",
        ),
        required_contained_pairs=(
            ("Position", "Core experiment controls"),
            ("Proportional gain Kp", "Core experiment controls"),
            ("Integral gain Ki", "Core experiment controls"),
            ("Derivative gain Kd", "Core experiment controls"),
            ("Force limit", "Core experiment controls"),
        ),
        required_text_metrics=(
            ("Position: 0.00 m", "#1D4ED8", 17),
            ("Force limit: 80 N", "#1D4ED8", 17),
        ),
        maximum_primary_actions=1,
        screenshot_ms=3000,
    ),
    AuditCase(
        "experiment_last_core_control_focus_640_en",
        640,
        360,
        "en",
        scenario="lab02.interactive-disturbance",
        actions=(
            "save_prediction,push,pause,key_tab,key_tab,key_tab,key_tab,key_tab,"
            "record_focus,accessibility_snapshot"
        ),
        accessibility=True,
        expect_focus_ring=True,
        expected_focus_names=(
            "Position",
            "Proportional gain Kp",
            "Integral gain Ki",
            "Derivative gain Kd",
            "Force limit",
            "Force limit",
        ),
        required_accessible_names=("Force limit", "Force limit: 80 N"),
        required_in_window_names=("Force limit", "Force limit: 80 N"),
        required_contained_pairs=(("Force limit", "Core experiment controls"),),
        required_text_metrics=(("Force limit: 80 N", "#1D4ED8", 17),),
        screenshot_ms=3600,
    ),
)

GL_CASE = AuditCase(
    "gl_threaded_640_ko",
    640,
    360,
    "ko",
    scenario="lab01.interactive-pull",
    actions="save_prediction,push,key_space,key_right",
    safe_mode=False,
)

GL_CAMERA_GESTURE_CASE = AuditCase(
    "gl_camera_gestures_1280_en",
    1280,
    720,
    "en",
    scenario="lab04.interactive-virtual-wall",
    actions=(
        "record_backend,orbit_scene,record_backend,pan_scene,record_backend,"
        "zoom_scene,record_backend,reset_camera,record_backend"
    ),
    safe_mode=False,
    require_camera_gesture_trace=True,
    required_scene_tokens=("current", "target", "wall"),
    minimum_robot_foreground_pixels=6_100,
    action_interval_ms=800,
    screenshot_ms=8000,
)

GL_CAMERA_KEYBOARD_CASE = AuditCase(
    "gl_camera_keyboard_640_en",
    640,
    360,
    "en",
    scenario="lab04.interactive-virtual-wall",
    actions=(
        "save_prediction,pause,record_backend,focus_scene,key_right,record_backend,"
        "key_shift_up,record_backend,key_plus,record_backend,key_zero,record_backend,"
        "accessibility_snapshot"
    ),
    safe_mode=False,
    accessibility=True,
    expect_focus_ring=True,
    require_camera_gesture_trace=True,
    required_scene_tokens=("current", "target", "wall"),
    minimum_robot_foreground_pixels=1_200,
    expected_transport_states=("paused",) * 5,
    stable_time_trace_pairs=((0, 1), (1, 2), (2, 3), (3, 4)),
    required_accessible_names=(
        "Scene markers: Current, Target, Force, Wall / constraint. "
        "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
    ),
    required_in_window_names=(
        "Scene markers: Current, Target, Force, Wall / constraint. "
        "Arrows: orbit · Shift+Arrows: pan · +/-: zoom · 0: reset",
    ),
    action_interval_ms=800,
    screenshot_ms=9800,
)

GL_CONTROL_PRECISION_CASE = AuditCase(
    "gl_control_precision_640_en",
    640,
    360,
    "en",
    scenario="lab04.interactive-virtual-wall",
    actions="save_prediction,pause,key_tab,key_right,accessibility_snapshot",
    safe_mode=False,
    accessibility=True,
    required_accessible_names=("Target X: 0.615 m",),
    required_in_window_names=("Target X: 0.615 m",),
    required_text_metrics=(("Target X: 0.615 m", "#1D4ED8", 17),),
    required_scene_tokens=("current", "target", "wall"),
    minimum_robot_foreground_pixels=1_200,
    screenshot_ms=4200,
)

GL_CORE_CONTROLS_CASE = AuditCase(
    "gl_core_controls_visible_1280_ko",
    1280,
    720,
    "ko",
    scenario="lab04.interactive-virtual-wall",
    actions="save_prediction,key_enter,pause,accessibility_snapshot",
    safe_mode=False,
    accessibility=True,
    required_accessible_names=(
        "핵심 실험 제어",
        "관찰",
        "예측 결과",
        "목표 X",
        "가상 벽 X",
        "벽 강성",
        "벽 감쇠",
        "벽 후퇴 게인",
    ),
    required_contained_pairs=(
        ("목표 X", "핵심 실험 제어"),
        ("가상 벽 X", "핵심 실험 제어"),
        ("벽 강성", "핵심 실험 제어"),
        ("벽 감쇠", "핵심 실험 제어"),
        ("벽 후퇴 게인", "핵심 실험 제어"),
    ),
    required_scene_tokens=("current", "target", "wall"),
    minimum_robot_foreground_pixels=6_100,
    maximum_primary_actions=1,
    action_interval_ms=800,
    screenshot_ms=5200,
)

GL_REPLAY_CASE = AuditCase(
    "gl_replay_wall_640_ko",
    640,
    360,
    "ko",
    page="results",
    actions="replay_fixture,pause,seek_50,accessibility_snapshot",
    expect_experiment=True,
    safe_mode=False,
    accessibility=True,
    fixture="valid_wall_replay",
    screenshot_ms=1900,
    required_scene_tokens=("current", "target", "wall", "force"),
    maximum_primary_actions=1,
    required_primary_names=("재생",),
)

GL_RESTART_CASE = AuditCase(
    "gl_restart_cleanup_640_ko",
    640,
    360,
    "ko",
    scenario="lab01.interactive-pull",
    actions=(
        "save_prediction,remember_session,finish_session,wait_worker,record_backend,"
        "pause,wait_restart,save_prediction,record_backend,remember_session,"
        "finish_session,wait_worker,record_backend,pause,wait_restart,save_prediction,"
        "record_backend,remember_session,finish_session,wait_worker,record_backend,"
        "pause,wait_restart,save_prediction,record_backend"
    ),
    safe_mode=False,
    expected_speed_trace=(1.0,) * 6,
    expected_transport_states=(
        "completed", "running", "completed", "running", "completed", "running"
    ),
    expected_cleanup_trace=(True,) * 6,
    maximum_rss_growth_kb=65_536,
    rss_ignore_initial_samples=1,
    action_interval_ms=800,
    screenshot_ms=24_000,
    auto_quit_grace_ms=12_000,
)

GL_CROSS_SCENARIO_CASE = AuditCase(
    "gl_cross_scenario_replace_640_ko",
    640,
    360,
    "ko",
    scenario="lab01.interactive-pull",
    actions=(
        "save_prediction,remember_session,finish_session,wait_worker,record_backend,"
        "start_next,record_backend"
    ),
    safe_mode=False,
    expected_speed_trace=(1.0, 1.0),
    expected_transport_states=("completed", "paused"),
    expected_cleanup_trace=(True, True),
    expected_pages=("experiment", "experiment"),
    required_scene_tokens=("current", "spring"),
    action_interval_ms=1_000,
    screenshot_ms=11_000,
    auto_quit_grace_ms=6_000,
)

GL_REPLAY_RESTART_CASE = AuditCase(
    "gl_replay_restart_reuse_640_ko",
    640,
    360,
    "ko",
    page="results",
    actions=(
        "replay_fixture,remember_session,record_backend,restart_replay_trace"
    ),
    safe_mode=False,
    fixture="valid_wall_replay",
    expect_experiment=True,
    expected_speed_trace=(1.0, 1.0),
    expected_transport_states=("completed", "replaying"),
    expected_cleanup_trace=(False, False),
    expect_no_session_replacement=True,
    action_interval_ms=800,
    screenshot_ms=6000,
    required_scene_tokens=("current", "target", "wall", "force"),
)

GL_RESULTS_RECOVERY_CASE = AuditCase(
    "gl_results_recovery_1280_en",
    1280,
    720,
    "en",
    page="results",
    actions="accessibility_snapshot",
    safe_mode=False,
    accessibility=True,
    fixture="many_results",
    required_accessible_names=(
        "Rerun same settings: LAB01 · Auto demo · Latest",
        "View report: LAB01 · Auto demo · Latest",
    ),
    forbidden_accessible_names=(
        "Replay recording: LAB01 · Auto demo · Latest",
    ),
    expected_accessible_controls=66,
    require_unique_control_names=True,
    maximum_primary_actions=1,
    required_primary_names=(
        "Rerun same settings: LAB01 · Auto demo · Latest",
    ),
)

GL_SCROLL_FOCUS_CASE = AuditCase(
    "gl_results_keyboard_scroll_640_en",
    640,
    360,
    "en",
    page="results",
    actions=(
        "focus_result_primary,key_tab,key_tab,key_tab,key_tab,key_tab,key_tab,"
        "key_backtab,key_backtab,key_backtab,key_backtab,accessibility_snapshot"
    ),
    safe_mode=False,
    accessibility=True,
    expect_focus_ring=True,
    fixture="many_results",
    expected_focus_names=(
        "Rerun same settings: LAB01 · Auto demo · Latest",
        "View report: LAB01 · Auto demo · Latest",
        "Manage: LAB01 · Auto demo · Latest",
        "Rerun same settings: LAB01 · Auto demo · Older 2",
        "View report: LAB01 · Auto demo · Older 2",
        "Manage: LAB01 · Auto demo · Older 2",
        "Rerun same settings: LAB01 · Auto demo · Older 3",
        "Manage: LAB01 · Auto demo · Older 2",
        "View report: LAB01 · Auto demo · Older 2",
        "Rerun same settings: LAB01 · Auto demo · Older 2",
        "Manage: LAB01 · Auto demo · Latest",
    ),
    required_in_window_names=(
        "LAB01 · Auto demo · Latest",
    ),
    required_context_above_pairs=((
        "LAB01 · Auto demo · Latest",
        "Manage: LAB01 · Auto demo · Latest",
    ),),
    action_interval_ms=300,
    screenshot_ms=4500,
)

GL_RESULTS_LOAD_FOCUS_CASE = AuditCase(
    "gl_results_load_keyboard_640_en",
    640,
    360,
    "en",
    page="results",
    actions=(
        "focus_results_load_more,press_enter,record_focus,"
        "focus_results_load_more,press_enter,record_focus,accessibility_snapshot"
    ),
    safe_mode=False,
    accessibility=True,
    expect_focus_ring=True,
    fixture="many_results",
    expected_focus_names=(
        "Show 20 more",
        "Rerun same settings: LAB01 · Auto demo · Older 21",
        "Show 20 more",
        "Rerun same settings: LAB01 · Auto demo · Older 41",
    ),
    required_accessible_names=(
        "Rerun same settings: LAB01 · Auto demo · Older 41",
        "Manage: LAB01 · Auto demo · Older 60",
    ),
    forbidden_accessible_names=("Show 20 more",),
    expected_accessible_controls=185,
    require_unique_control_names=True,
    required_in_window_names=(
        "LAB01 · Auto demo · Older 41",
    ),
    required_context_above_pairs=((
        "LAB01 · Auto demo · Older 41",
        "Rerun same settings: LAB01 · Auto demo · Older 41",
    ),),
    action_interval_ms=400,
    screenshot_ms=4300,
)

GL_EVIDENCE_HANDOFF_CASE = AuditCase(
    "gl_evidence_handoff_640_en",
    640,
    360,
    "en",
    scenario="lab01.interactive-pull",
    actions=(
        "save_prediction,push,pause,type_observation,key_tab,key_down,key_tab,key_enter,"
        "record_backend,accessibility_snapshot"
    ),
    safe_mode=False,
    accessibility=True,
    expected_focus_names=(
        "Observe",
        "Prediction outcome",
        "Prediction outcome",
        "Save observation",
        "Play",
    ),
    expected_evidence_trace=((True, True, True, 4),),
    expected_transport_states=("paused",),
    required_accessible_names=(
        "✓ Evidence saved",
        "Core experiment controls",
        "Play",
    ),
    required_contained_pairs=(("✓ Evidence saved", "Core experiment controls"),),
    maximum_primary_actions=1,
    required_primary_names=("Play",),
    action_interval_ms=350,
    screenshot_ms=4200,
)


def _pixels(path: Path) -> np.ndarray:
    image = QImage(str(path)).convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    data = np.frombuffer(image.bits(), dtype=np.uint8, count=image.sizeInBytes())
    return data.reshape(height, image.bytesPerLine())[:, : width * 4].reshape(height, width, 4).copy()


def _longest_scene_run(pixels: np.ndarray, x: int = 20) -> int:
    sample = pixels[:, min(x, pixels.shape[1] - 1), :3].astype(float)
    # A teaching viewport may intentionally combine a dark 3D background with a
    # bright floor. Measure its continuous departure from the app background
    # instead of treating the accessible light floor as lost viewport height.
    scene = np.linalg.norm(sample - np.asarray((245.0, 247.0, 251.0)), axis=1) > 24.0
    longest = current = 0
    for value in scene:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _scene_token_distances(pixels: np.ndarray, names: tuple[str, ...]) -> dict[str, float]:
    height, width = pixels.shape[:2]
    # Score the physical teaching scene itself. The top prompt and bottom legend
    # intentionally repeat semantic colors, so including them would let an empty
    # safe-mode viewport pass without showing the actual plant.
    # The wide experiment layout devotes roughly the left 73% to the scene.
    # Keep the right control panel out, but do not crop markers near the hand.
    viewport = pixels[int(height * 0.43) : int(height * 0.64), : int(width * 0.73), :3]
    sample = viewport.reshape(-1, 3).astype(float)
    return {
        name: float(np.linalg.norm(sample - rgb(SEMANTIC_COLORS[name]), axis=1).min())
        for name in names
    }


def _scene_token_pixel_counts(
    pixels: np.ndarray, requirements: tuple[tuple[str, int], ...]
) -> dict[str, int]:
    """Measure whether semantic teaching marks remain prominent on wide screens."""

    height, width = pixels.shape[:2]
    # Exclude app chrome and the right controls while retaining the full plant,
    # its labels, floor, target, and force arrow in the central viewport.
    viewport = pixels[int(height * 0.18) : int(height * 0.88), : int(width * 0.82), :3]
    sample = viewport.astype(np.int16)
    counts: dict[str, int] = {}
    for name, _minimum in requirements:
        token = np.asarray(rgb(SEMANTIC_COLORS[name]), dtype=np.int16)
        distance = np.linalg.norm(sample - token, axis=2)
        counts[name] = int((distance <= 3.0).sum())
    return counts


def _robot_foreground_pixel_count(pixels: np.ndarray) -> int:
    """Estimate the visible Panda body area without counting scene HUD text."""

    height, width = pixels.shape[:2]
    viewport = pixels[
        int(height * 0.45) : int(height * 0.68),
        int(width * 0.25) : int(width * 0.55),
        :3,
    ]
    minimum = viewport.min(axis=2)
    spread = viewport.max(axis=2) - minimum
    return int(((minimum >= 170) & (spread <= 70)).sum())


def _control_color_distance(
    pixels: np.ndarray,
    item: dict[str, object],
    window: dict[str, object],
    color: str,
) -> float:
    """Measure a design token inside one accessible control's rendered bounds."""

    left, top, logical_width, logical_height = window["rect"]
    x, y, width, height = item["rect"]
    scale_x = pixels.shape[1] / logical_width
    scale_y = pixels.shape[0] / logical_height
    x0 = max(0, round((x - left) * scale_x))
    y0 = max(0, round((y - top) * scale_y))
    x1 = min(pixels.shape[1], round((x + width - left) * scale_x))
    y1 = min(pixels.shape[0], round((y + height - top) * scale_y))
    if x1 <= x0 or y1 <= y0:
        return float("inf")
    sample = pixels[y0:y1, x0:x1, :3].reshape(-1, 3).astype(float)
    return float(np.linalg.norm(sample - rgb(color), axis=1).min())


def _control_color_pixels(
    pixels: np.ndarray,
    item: dict[str, object],
    window: dict[str, object],
    color: str,
) -> int:
    """Count a design token across an accessible control's rendered bounds."""

    left, top, logical_width, logical_height = window["rect"]
    x, y, width, height = item["rect"]
    scale_x = pixels.shape[1] / logical_width
    scale_y = pixels.shape[0] / logical_height
    x0 = max(0, round((x - left) * scale_x))
    y0 = max(0, round((y - top) * scale_y))
    x1 = min(pixels.shape[1], round((x + width - left) * scale_x))
    y1 = min(pixels.shape[0], round((y + height - top) * scale_y))
    if x1 <= x0 or y1 <= y0:
        return 0
    sample = pixels[y0:y1, x0:x1, :3].reshape(-1, 3).astype(float)
    return int((np.linalg.norm(sample - rgb(color), axis=1) <= 24.0).sum())


def _control_border_color_distance(
    pixels: np.ndarray,
    item: dict[str, object],
    window: dict[str, object],
    color: str,
) -> float:
    """Measure a design token only along an accessible control's perimeter."""

    left, top, logical_width, logical_height = window["rect"]
    x, y, width, height = item["rect"]
    scale_x = pixels.shape[1] / logical_width
    scale_y = pixels.shape[0] / logical_height
    x0 = max(0, round((x - left) * scale_x))
    y0 = max(0, round((y - top) * scale_y))
    x1 = min(pixels.shape[1], round((x + width - left) * scale_x))
    y1 = min(pixels.shape[0], round((y + height - top) * scale_y))
    if x1 <= x0 or y1 <= y0:
        return float("inf")
    band_x = max(1, round(3 * scale_x))
    band_y = max(1, round(3 * scale_y))
    perimeter = np.concatenate(
        (
            pixels[y0 : min(y1, y0 + band_y), x0:x1, :3].reshape(-1, 3),
            pixels[max(y0, y1 - band_y) : y1, x0:x1, :3].reshape(-1, 3),
            pixels[y0:y1, x0 : min(x1, x0 + band_x), :3].reshape(-1, 3),
            pixels[y0:y1, max(x0, x1 - band_x) : x1, :3].reshape(-1, 3),
        )
    ).astype(float)
    return float(np.linalg.norm(perimeter - rgb(color), axis=1).min())


def _control_border_color_pixels(
    pixels: np.ndarray,
    item: dict[str, object],
    window: dict[str, object],
    color: str,
) -> int:
    """Count design-token pixels along an accessible surface perimeter."""

    left, top, logical_width, logical_height = window["rect"]
    x, y, width, height = item["rect"]
    scale_x = pixels.shape[1] / logical_width
    scale_y = pixels.shape[0] / logical_height
    x0 = max(0, round((x - left) * scale_x))
    y0 = max(0, round((y - top) * scale_y))
    x1 = min(pixels.shape[1], round((x + width - left) * scale_x))
    y1 = min(pixels.shape[0], round((y + height - top) * scale_y))
    if x1 <= x0 or y1 <= y0:
        return 0
    band_x = max(1, round(3 * scale_x))
    band_y = max(1, round(3 * scale_y))
    perimeter = np.concatenate(
        (
            pixels[y0 : min(y1, y0 + band_y), x0:x1, :3].reshape(-1, 3),
            pixels[max(y0, y1 - band_y) : y1, x0:x1, :3].reshape(-1, 3),
            pixels[y0:y1, x0 : min(x1, x0 + band_x), :3].reshape(-1, 3),
            pixels[y0:y1, max(x0, x1 - band_x) : x1, :3].reshape(-1, 3),
        )
    ).astype(float)
    return int((np.linalg.norm(perimeter - rgb(color), axis=1) <= 24.0).sum())


def _control_text_vertical_span(
    pixels: np.ndarray,
    item: dict[str, object],
    window: dict[str, object],
) -> float:
    """Measure the body-text glyph span to the right of a checkbox indicator."""

    left, top, logical_width, logical_height = window["rect"]
    x, y, width, height = item["rect"]
    scale_x = pixels.shape[1] / logical_width
    scale_y = pixels.shape[0] / logical_height
    x0 = max(0, round((x - left + min(42, width)) * scale_x))
    y0 = max(0, round((y - top + min(6, height / 4)) * scale_y))
    x1 = min(
        pixels.shape[1],
        round((x + width - left - min(6, width / 4)) * scale_x),
    )
    y1 = min(
        pixels.shape[0],
        round((y + height - top - min(6, height / 4)) * scale_y),
    )
    if x1 <= x0 or y1 <= y0:
        return float("inf")
    sample = pixels[y0:y1, x0:x1, :3].astype(float)
    # Thin 1x glyphs may contain no exact body-text token pixel after
    # antialiasing.  The secondary-text token stays close enough to both the
    # dark enabled label and its antialiased edge while remaining far from the
    # white card and yellow/black focus ring.
    glyphs = np.linalg.norm(sample - rgb("#64748B"), axis=2) <= 60.0
    rows = np.flatnonzero(glyphs.any(axis=1))
    if rows.size == 0:
        return float("inf")
    return float((rows[-1] - rows[0] + 1) / scale_y)


def _control_indicator_color_pixels(
    pixels: np.ndarray,
    item: dict[str, object],
    window: dict[str, object],
    color: str,
) -> int:
    """Count token-colored pixels in a checkbox's left indicator square."""

    left, top, logical_width, logical_height = window["rect"]
    x, y, _width, height = item["rect"]
    scale_x = pixels.shape[1] / logical_width
    scale_y = pixels.shape[0] / logical_height
    x0 = max(0, round((x - left) * scale_x))
    y0 = max(0, round((y - top) * scale_y))
    x1 = min(pixels.shape[1], x0 + round(height * scale_x))
    y1 = min(pixels.shape[0], y0 + round(height * scale_y))
    if x1 <= x0 or y1 <= y0:
        return 0
    sample = pixels[y0:y1, x0:x1, :3].astype(float)
    distance = np.linalg.norm(sample - rgb(color), axis=2)
    return int((distance <= 24.0).sum())


def _primary_button_names(
    pixels: np.ndarray,
    items: list[dict[str, object]],
    window: dict[str, object] | None,
) -> list[str]:
    """Return enabled buttons whose filled area uses the primary-action blue."""

    if window is None:
        return []
    left, top, logical_width, logical_height = window["rect"]
    if logical_width <= 0 or logical_height <= 0:
        return []
    scale_x = pixels.shape[1] / logical_width
    scale_y = pixels.shape[0] / logical_height
    primary = np.array(rgb("#2563EB"), dtype=np.int16)
    names: list[str] = []
    for item in items:
        if (
            item.get("role") != "Button"
            or item.get("invisible")
            or item.get("disabled")
        ):
            continue
        x, y, width, height = item.get("rect", [0, 0, 0, 0])
        x0 = max(0, round((x - left) * scale_x))
        y0 = max(0, round((y - top) * scale_y))
        x1 = min(pixels.shape[1], round((x + width - left) * scale_x))
        y1 = min(pixels.shape[0], round((y + height - top) * scale_y))
        crop = pixels[y0:y1, x0:x1, :3]
        if crop.size == 0:
            continue
        difference = np.abs(crop.astype(np.int16) - primary)
        if float(np.all(difference <= 6, axis=2).mean()) >= 0.20:
            names.append(str(item.get("name", "")))
    return names


def _prepare_fixture(name: str, data_root: Path) -> None:
    if not name:
        return
    run = data_root / "outputs" / name
    run.mkdir(parents=True, exist_ok=True)
    if name in {
        "path_partial",
        "path_scenarios_complete",
        "path_batch_running",
        "path_complete",
    }:
        statuses = (
            ["completed", "completed", "stopped", "error"]
            if name == "path_partial"
            else ["completed"] * len(LEARNING_PATH_SCENARIO_IDS)
        )
        for index, (scenario_id, status) in enumerate(
            zip(LEARNING_PATH_SCENARIO_IDS, statuses, strict=False)
        ):
            saved = run if index == 0 else data_root / "outputs" / f"{name}_{index:02d}"
            saved.mkdir(parents=True, exist_ok=True)
            (saved / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "scenario_id": scenario_id,
                        "status": status,
                        "config": {"resolved": {"sim_time": 1.0}},
                    }
                ),
                encoding="utf-8",
            )
        if name in {"path_batch_running", "path_complete"}:
            batch = data_root / "outputs" / f"{name}_batch"
            batch.mkdir()
            batch_status = "running" if name == "path_batch_running" else "completed"
            (batch / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "scenario_id": ALL_COMPARE_ID,
                        "status": batch_status,
                    }
                ),
                encoding="utf-8",
            )
            if batch_status == "completed":
                (batch / "summary.json").write_text(
                    json.dumps(
                        {
                            "batch_name": "all",
                            "child_batches": 5,
                            "scenario_runs": 54,
                            "duration": 12.5,
                        }
                    ),
                    encoding="utf-8",
                )
                (batch / "report.html").write_text(
                    '<html lang="ko"><h1>All compare</h1></html>',
                    encoding="utf-8",
                )
            newest = time.time_ns() + 2_000_000_000
            os.utime(batch, ns=(newest, newest))
        return
    if name == "corrupt_replay":
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scenario_id": "lab01.default",
                    "status": "completed",
                    "config": {"resolved": {"mass": 1.0, "sim_time": 1.0}},
                }
            ),
            encoding="utf-8",
        )
        (run / "config.yaml").write_text("mass: 1.0\nsim_time: 1.0\n", encoding="utf-8")
        (run / "replay.npz").write_bytes(b"injected corrupt replay")
        return
    if name in {"valid_replay", "dense_replay"}:
        frame_count = 61
        timeline = np.linspace(0.0, 1.0, frame_count)
        positions = 0.3 * np.sin(2.0 * np.pi * timeline)
        events = [
            {"time": 0.25, "kind": "button", "name": "push"},
            {"time": 0.75, "kind": "slider", "name": "damping"},
        ]
        if name == "dense_replay":
            events = [
                *(
                    {"time": 0.1 + index * 0.002, "kind": "learner", "name": "orbit"}
                    for index in range(119)
                ),
                *(
                    {"time": 0.2 + index * 0.01, "kind": "slider", "name": "damping"}
                    for index in range(10)
                ),
                {"time": 0.8, "kind": "button", "name": "push"},
            ]
            events.sort(key=lambda event: float(event["time"]))
        np.savez_compressed(
            run / "replay.npz",
            schema_version=np.asarray([1], dtype=np.int16),
            time=timeline,
            qpos=positions.reshape(-1, 1).astype(np.float32),
            qvel=np.gradient(positions, timeline).reshape(-1, 1).astype(np.float32),
            ctrl=np.zeros((frame_count, 1), dtype=np.float32),
            semantic_keys=np.asarray(
                ["time", "position", "velocity", "target_position", "force"],
                dtype=str,
            ),
            semantic__time=timeline.astype(np.float32),
            semantic__position=positions.astype(np.float32),
            semantic__velocity=np.gradient(positions, timeline).astype(np.float32),
            semantic__target_position=np.zeros(frame_count, dtype=np.float32),
            semantic__force=np.zeros(frame_count, dtype=np.float32),
            events_json=np.asarray(
                [json.dumps(events)],
                dtype=str,
            ),
        )
        (run / "config.yaml").write_text(
            "model_path: models/lab01_msd/scene.xml\nsim_time: 1.0\n",
            encoding="utf-8",
        )
        (run / "summary.json").write_text(
            json.dumps(
                {
                    "lab_name": "lab01_msd",
                    "duration": 1.0,
                    "max_abs_position": 0.3,
                    "interaction_events": 2,
                }
            ),
            encoding="utf-8",
        )
        (run / "report.html").write_text(
            '<html lang="ko"><h1>Replay fixture report</h1></html>',
            encoding="utf-8",
        )
        write_manifest(
            run,
            scenario_id="lab01.interactive-pull",
            status="completed",
            config={
                "model_path": "models/lab01_msd/scene.xml",
                "sim_time": 1.0,
                "mass": 1.0,
                "damping": 0.8,
                "stiffness": 30.0,
            },
        )
        return
    if name == "valid_wall_replay":
        frame_count = 61
        timeline = np.linspace(0.0, 1.0, frame_count)
        qpos = np.tile(
            np.asarray([0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853, 0.04, 0.04]),
            (frame_count, 1),
        )
        hand_x = np.linspace(0.50, 0.55, frame_count)
        np.savez_compressed(
            run / "replay.npz",
            schema_version=np.asarray([1], dtype=np.int16),
            time=timeline,
            qpos=qpos.astype(np.float32),
            qvel=np.zeros((frame_count, 9), dtype=np.float32),
            ctrl=np.zeros((frame_count, 8), dtype=np.float32),
            semantic_keys=np.asarray(
                [
                    "time",
                    "hand_x",
                    "hand_y",
                    "hand_z",
                    "target_x",
                    "target_y",
                    "target_z",
                    "wall_x",
                    "wall_force_x",
                    "wall_penetration",
                ],
                dtype=str,
            ),
            semantic__time=timeline.astype(np.float32),
            semantic__hand_x=hand_x.astype(np.float32),
            semantic__hand_y=np.zeros(frame_count, dtype=np.float32),
            semantic__hand_z=np.full(frame_count, 0.58, dtype=np.float32),
            semantic__target_x=np.full(frame_count, 0.64, dtype=np.float32),
            semantic__target_y=np.zeros(frame_count, dtype=np.float32),
            semantic__target_z=np.full(frame_count, 0.58, dtype=np.float32),
            semantic__wall_x=np.full(frame_count, 0.53, dtype=np.float32),
            semantic__wall_force_x=np.full(frame_count, -30.0, dtype=np.float32),
            semantic__wall_penetration=np.linspace(0.0, 2.0, frame_count).astype(np.float32),
            events_json=np.asarray(
                [json.dumps([{"time": 0.5, "kind": "preset", "name": "Close wall"}])],
                dtype=str,
            ),
        )
        model_path = "third_party/mujoco_menagerie/franka_emika_panda/scene.xml"
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scenario_id": "lab04.interactive-virtual-wall",
                    "status": "completed",
                    "model": {"path": model_path},
                    "config": {
                        "resolved": {
                            "model_path": model_path,
                            "sim_time": 1.0,
                            "mode": "impedance_wall",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (run / "config.yaml").write_text(
            f"model_path: {model_path}\nsim_time: 1.0\nmode: impedance_wall\n",
            encoding="utf-8",
        )
        return
    if name == "many_results":
        for index in range(60):
            saved = data_root / "outputs" / f"saved_{index:03d}"
            saved.mkdir(parents=True, exist_ok=True)
            (saved / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "scenario_id": "lab01.default",
                        "status": "completed",
                        "config": {"resolved": {"mass": 1.0, "sim_time": 1.0}},
                    }
                ),
                encoding="utf-8",
            )
            (saved / "summary.json").write_text(
                json.dumps(
                    {
                        "duration": 1.0,
                        "max_abs_position": index / 100.0,
                        "interaction_events": index % 3,
                    }
                ),
                encoding="utf-8",
            )
            (saved / "config.yaml").write_text("mass: 1.0\nsim_time: 1.0\n", encoding="utf-8")
            (saved / "report.html").write_text("<html><h1>Saved run</h1></html>", encoding="utf-8")
        return
    raise ValueError(f"Unknown UI audit fixture: {name}")


def _run_case(case: AuditCase, output: Path, settings: Path) -> AuditResult:
    screenshot = output / f"{case.name}.png"
    run_output = output / f"{case.name}_run"
    data_root = settings / case.name / "data"
    _prepare_fixture(case.fixture, data_root)
    env = {
        **os.environ,
        "QT_QUICK_BACKEND": "software",
        "XDG_CONFIG_HOME": str(settings / case.name),
        "MCLAB_OUTPUT_DIR": str(run_output),
        "MCLAB_DATA_DIR": str(data_root),
        "MCLAB_WINDOW_WIDTH": str(case.width),
        "MCLAB_WINDOW_HEIGHT": str(case.height),
        "MCLAB_APP_AUTO_QUIT_MS": str(
            max(1900, case.screenshot_ms + case.auto_quit_grace_ms)
        ),
        "MCLAB_SCREENSHOT_MS": str(case.screenshot_ms),
        "MCLAB_SCREENSHOT_PATH": str(screenshot),
        "MCLAB_FAIL_ON_ERROR": "1",
        "MCLAB_SELF_TEST": "1",
        "MCLAB_INSTANCE_LOCK": str(settings / case.name / "mclab-ui-audit.lock"),
        "QT_SCALE_FACTOR": str(case.device_scale),
        "PYTHONFAULTHANDLER": "1",
    }
    if not case.safe_mode:
        env["MUJOCO_GL"] = "egl"
    actions = [] if case.page == "home" else [f"navigate_{case.page}"]
    if case.actions:
        actions.extend(case.actions.split(","))
    if actions:
        env["MCLAB_SMOKE_ACTION"] = ",".join(actions)
        env["MCLAB_SMOKE_ACTION_MS"] = "250"
        env["MCLAB_SMOKE_ACTION_INTERVAL_MS"] = str(case.action_interval_ms)
    focus_trace_path = output / f"{case.name}_focus.json"
    trace_focus = any(
        action.startswith(("key_", "focus_", "type_")) or action == "record_focus"
        for action in actions
    )
    if trace_focus:
        focus_trace_path.unlink(missing_ok=True)
        env["MCLAB_FOCUS_TRACE_PATH"] = str(focus_trace_path)
    backend_trace_path = output / f"{case.name}_backend.json"
    if "record_backend" in actions:
        backend_trace_path.unlink(missing_ok=True)
        env["MCLAB_BACKEND_TRACE_PATH"] = str(backend_trace_path)
    accessibility_path = output / f"{case.name}_accessibility.json"
    if case.accessibility:
        env["MCLAB_ACCESSIBILITY_PATH"] = str(accessibility_path)
    if case.fixture:
        env["MCLAB_FIXTURE_RUN_PATH"] = str(data_root / "outputs" / case.fixture)
    command = [sys.executable, "-m", "mclab", "app"]
    if case.safe_mode:
        command.append("--safe-mode")
    command.extend(("--lang", case.language))
    if case.scenario:
        command.extend(("--scenario", case.scenario))
    completed = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    if completed.stdout:
        (output / f"{case.name}_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    if completed.stderr:
        (output / f"{case.name}_stderr.txt").write_text(completed.stderr, encoding="utf-8")
    notes: list[str] = []
    expected_return = 5 if case.expect_error else 0
    passed = completed.returncode == expected_return and screenshot.is_file()
    if completed.returncode != expected_return:
        notes.append(f"app exit {completed.returncode}")
    if not screenshot.is_file():
        return AuditResult(
            case.name,
            False,
            completed.returncode,
            str(screenshot),
            "missing",
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            notes,
        )
    pixels = _pixels(screenshot)
    dimensions = f"{pixels.shape[1]}x{pixels.shape[0]}"
    expected_dimensions = (
        f"{round(case.width * case.device_scale)}x{round(case.height * case.device_scale)}"
    )
    if dimensions != expected_dimensions:
        passed = False
        notes.append(f"expected {expected_dimensions}")
    pure_black = int(np.all(pixels[:, :, :3] < 8, axis=2).sum())
    is_experiment = bool(case.scenario or case.expect_experiment) and not case.expect_non_experiment
    viewport_run = _longest_scene_run(pixels) if is_experiment else None
    focus_yellow_pixels = None
    warning_amber_pixels = None
    tour_connector_pixels = None
    task_action_count = None
    if case.expect_focus_ring:
        yellow = (
            (pixels[:, :, 0] >= 235)
            & (pixels[:, :, 1] >= 185)
            & (pixels[:, :, 1] <= 235)
            & (pixels[:, :, 2] <= 45)
        )
        focus_yellow_pixels = int(yellow.sum())
        if focus_yellow_pixels < 40:
            passed = False
            notes.append("keyboard focus ring has fewer than 40 yellow pixels")
        if pure_black < 20:
            passed = False
            notes.append("keyboard focus ring has fewer than 20 black outline pixels")
    if (
        case.minimum_tour_connector_pixels is not None
        or case.maximum_tour_connector_pixels is not None
    ):
        connector = np.asarray(rgb(TOUR_CONNECTOR_COLOR), dtype=np.int16)
        difference = np.abs(pixels[:, :, :3].astype(np.int16) - connector)
        tour_connector_pixels = int(np.all(difference <= 3, axis=2).sum())
        if (
            case.minimum_tour_connector_pixels is not None
            and tour_connector_pixels < case.minimum_tour_connector_pixels
        ):
            passed = False
            notes.append(
                f"tour connectors have {tour_connector_pixels} pixels; "
                f"minimum is {case.minimum_tour_connector_pixels}"
            )
        if (
            case.maximum_tour_connector_pixels is not None
            and tour_connector_pixels > case.maximum_tour_connector_pixels
        ):
            passed = False
            notes.append(
                f"tour connectors have {tour_connector_pixels} pixels; "
                f"maximum is {case.maximum_tour_connector_pixels}"
            )
    if case.expect_setup_warning:
        amber = (
            (pixels[:, :, 0] >= 140)
            & (pixels[:, :, 0] <= 245)
            & (pixels[:, :, 1] >= 75)
            & (pixels[:, :, 1] <= 200)
            & (pixels[:, :, 2] <= 110)
        )
        warning_amber_pixels = int(amber.sum())
        if warning_amber_pixels < 80:
            passed = False
            notes.append("setup warning has fewer than 80 amber pixels")
    if case.maximum_actions is not None:
        task_action_count = len([item for item in case.actions.split(",") if item])
        if task_action_count > case.maximum_actions:
            passed = False
            notes.append(
                f"task used {task_action_count} actions; limit is {case.maximum_actions}"
            )
    non_scene_black_limit = round(5_000 * max(1.0, case.device_scale**2))
    if not is_experiment and pure_black > non_scene_black_limit:
        passed = False
        notes.append(
            "text and focus outlines cannot explain "
            f"{pure_black} black pixels on a non-scene page "
            f"(scale-adjusted limit {non_scene_black_limit})"
        )
    if is_experiment and not case.expect_error and case.width == 640 and (viewport_run or 0) < 140:
        passed = False
        notes.append("compact experiment viewport is under 140 px tall")
    scene_token_distance = None
    if case.required_scene_tokens:
        scene_token_distance = _scene_token_distances(pixels, case.required_scene_tokens)
        for name, distance in scene_token_distance.items():
            if distance > 80.0:
                passed = False
                notes.append(f"{name} scene marker is not visibly close to its semantic token")
    scene_token_pixels = None
    if case.minimum_scene_token_pixels:
        scene_token_pixels = _scene_token_pixel_counts(
            pixels, case.minimum_scene_token_pixels
        )
        for name, minimum in case.minimum_scene_token_pixels:
            measured = scene_token_pixels[name]
            if measured < minimum:
                passed = False
                notes.append(
                    f"{name} scene marker has {measured} pixels; minimum is {minimum}"
                )
    robot_foreground_pixels = None
    if case.minimum_robot_foreground_pixels is not None:
        robot_foreground_pixels = _robot_foreground_pixel_count(pixels)
        if robot_foreground_pixels < case.minimum_robot_foreground_pixels:
            passed = False
            notes.append(
                f"robot foreground has {robot_foreground_pixels} pixels; "
                f"minimum is {case.minimum_robot_foreground_pixels}"
            )
    accessible_controls = unnamed_controls = scenario_start_buttons = None
    scenario_context_titles = None
    control_color_distance = None
    control_color_pixels = None
    control_border_color_distance = None
    role_border_color_pixels = None
    indicator_color_pixels = None
    text_metric_values = None
    control_text_vertical_spans = None
    undersized_targets = None
    primary_actions = None
    primary_action_names = None
    if case.accessibility:
        if not accessibility_path.is_file():
            passed = False
            notes.append("accessibility tree is missing")
        else:
            items = json.loads(accessibility_path.read_text(encoding="utf-8"))["items"]
            interactive_roles = {"Button", "Slider", "CheckBox", "ComboBox", "EditableText"}
            controls = [
                item
                for item in items
                if item["role"] in interactive_roles and not item["invisible"]
            ]
            window = next((item for item in items if item["role"] == "Window"), None)
            if case.maximum_primary_actions is not None or case.required_primary_names:
                primary_action_names = _primary_button_names(pixels, items, window)
                primary_actions = len(primary_action_names)
            if case.maximum_primary_actions is not None:
                if primary_actions > case.maximum_primary_actions:
                    passed = False
                    notes.append(
                        f"found {primary_actions} primary actions; "
                        f"limit is {case.maximum_primary_actions}"
                    )
            for name in case.required_primary_names:
                if primary_action_names is None or name not in primary_action_names:
                    passed = False
                    notes.append(f"required primary action is not filled blue: {name}")
            outside_targets = []
            if window is not None:
                left, top, window_width, window_height = window["rect"]
                right = left + window_width
                bottom = top + window_height
                for item in controls:
                    x, y, width, height = item.get("rect", [0, 0, 0, 0])
                    intersects = (
                        x < right and x + width > left and y < bottom and y + height > top
                    )
                    if intersects and (
                        x < left or y < top or x + width > right or y + height > bottom
                    ):
                        outside_targets.append((item["name"], x, y, width, height))
            if case.require_no_partially_clipped_controls and outside_targets:
                passed = False
                sample = ", ".join(
                    f"{name}: {x},{y} {width}x{height}"
                    for name, x, y, width, height in outside_targets[:4]
                )
                notes.append(
                    f"{len(outside_targets)} visible control(s) cross the window edge: {sample}"
                )
            small_targets = []
            for item in controls:
                width, height = item.get("rect", [0, 0, 0, 0])[2:]
                marker = item["name"].startswith(("조작 이벤트:", "Interaction event:"))
                minimum = 24 if marker or item["role"] in {"Slider", "CheckBox"} else 44
                if width < minimum or height < minimum:
                    small_targets.append((item["role"], item["name"], width, height, minimum))
            undersized_targets = len(small_targets)
            if small_targets:
                passed = False
                sample = ", ".join(
                    f"{name or role}: {width}x{height}<{minimum}"
                    for role, name, width, height, minimum in small_targets[:4]
                )
                notes.append(f"{len(small_targets)} undersized control target(s): {sample}")
            starts = [
                item
                for item in controls
                if item["role"] == "Button"
                and item["name"].startswith(("Start", "시작"))
            ]
            accessible_controls = len(controls)
            unnamed_controls = sum(not item["name"].strip() for item in controls)
            scenario_start_buttons = len(starts)
            if unnamed_controls:
                passed = False
                notes.append(f"{unnamed_controls} visible controls have no accessible name")
            if (
                case.expected_accessible_controls is not None
                and len(controls) != case.expected_accessible_controls
            ):
                passed = False
                notes.append(
                    f"expected {case.expected_accessible_controls} visible controls, found {len(controls)}"
                )
            if case.require_unique_control_names and len({item["name"] for item in controls}) != len(
                controls
            ):
                passed = False
                notes.append("visible control names are not unique")
            if case.expected_scenario_starts is not None:
                expected = case.expected_scenario_starts
                if len(starts) != expected or len({item["name"] for item in starts}) != expected:
                    passed = False
                    notes.append(
                        f"scenario start buttons are not {expected} unique contextual names"
                    )
                if any(not item["description"].strip() for item in starts):
                    passed = False
                    notes.append("a scenario start button has no purpose description")
                contextual_names = {
                    item["name"].split(": ", 1)[1]
                    for item in starts
                    if ": " in item["name"]
                }
                static_names = {
                    item["name"]
                    for item in items
                    if item["role"] == "StaticText" and not item["invisible"]
                }
                matched_titles = contextual_names & static_names
                scenario_context_titles = len(matched_titles)
                if len(contextual_names) != expected or len(matched_titles) != expected:
                    passed = False
                    missing = sorted(contextual_names - static_names)
                    notes.append(
                        "visible scenario titles do not preserve all lab contexts: "
                        f"{len(matched_titles)}/{expected}; missing {missing[:3]}"
                    )
            if case.expected_disabled_scenario_starts is not None:
                disabled_starts = sum(bool(item["disabled"]) for item in starts)
                if disabled_starts != case.expected_disabled_scenario_starts:
                    passed = False
                    notes.append(
                        "expected "
                        f"{case.expected_disabled_scenario_starts} disabled scenario starts, "
                        f"found {disabled_starts}"
                    )
            if any(not item["focusable"] for item in controls if not item["disabled"]):
                passed = False
                notes.append("a visible interactive control is not keyboard focusable")
            visible_by_name = {
                item["name"]: item for item in items if item["name"] and not item["invisible"]
            }
            if case.expected_visible_dialog_names is not None:
                visible_dialog_names = tuple(
                    item["name"]
                    for item in items
                    if item["role"] == "Dialog" and not item["invisible"]
                )
                if visible_dialog_names != case.expected_visible_dialog_names:
                    passed = False
                    notes.append(
                        "visible dialog names are not exactly "
                        f"{case.expected_visible_dialog_names!r}: {visible_dialog_names!r}"
                    )
            if case.required_control_colors:
                control_color_distance = {}
                for name, color in case.required_control_colors:
                    item = visible_by_name.get(name)
                    key = f"{name}:{color}"
                    if item is None or window is None:
                        passed = False
                        control_color_distance[key] = float("inf")
                        notes.append(f"control color target is unavailable: {key}")
                        continue
                    distance = _control_color_distance(pixels, item, window, color)
                    control_color_distance[key] = distance
                    if distance > 24.0:
                        passed = False
                        notes.append(
                            f"control color {key} has pixel distance {distance:.1f}; limit is 24"
                        )
            if case.required_control_color_pixels:
                control_color_pixels = {}
                for name, color, minimum in case.required_control_color_pixels:
                    item = visible_by_name.get(name)
                    key = f"{name}:{color}"
                    if item is None or window is None:
                        passed = False
                        control_color_pixels[key] = 0
                        notes.append(f"control color pixel target is unavailable: {key}")
                        continue
                    count = _control_color_pixels(pixels, item, window, color)
                    control_color_pixels[key] = count
                    if count < minimum:
                        passed = False
                        notes.append(
                            f"control color {key} has {count} pixels; minimum is {minimum}"
                        )
            if case.required_control_border_colors or case.required_role_border_colors:
                control_border_color_distance = {}
                for name, color in case.required_control_border_colors:
                    item = visible_by_name.get(name)
                    key = f"{name}:{color}"
                    if item is None or window is None:
                        passed = False
                        control_border_color_distance[key] = float("inf")
                        notes.append(f"control border color target is unavailable: {key}")
                        continue
                    distance = _control_border_color_distance(pixels, item, window, color)
                    control_border_color_distance[key] = distance
                    if distance > 24.0:
                        passed = False
                        notes.append(
                            f"control border color {key} has pixel distance {distance:.1f}; "
                            "limit is 24"
                        )
                role_border_color_pixels = {}
                for role, name, color, minimum in case.required_role_border_colors:
                    item = next(
                        (
                            candidate
                            for candidate in items
                            if candidate["role"] == role
                            and candidate["name"] == name
                            and not candidate["invisible"]
                        ),
                        None,
                    )
                    key = f"{role}:{name}:{color}"
                    if item is None or window is None:
                        passed = False
                        control_border_color_distance[key] = float("inf")
                        role_border_color_pixels[key] = 0
                        notes.append(f"role border color target is unavailable: {key}")
                        continue
                    distance = _control_border_color_distance(pixels, item, window, color)
                    count = _control_border_color_pixels(pixels, item, window, color)
                    control_border_color_distance[key] = distance
                    role_border_color_pixels[key] = count
                    if distance > 24.0:
                        passed = False
                        notes.append(
                            f"role border color {key} has pixel distance {distance:.1f}; "
                            "limit is 24"
                        )
                    if count < minimum:
                        passed = False
                        notes.append(
                            f"role border color {key} has {count} pixels; "
                            f"minimum is {minimum}"
                        )
            if case.required_indicator_colors:
                indicator_color_pixels = {}
                for name, color, minimum in case.required_indicator_colors:
                    item = next(
                        (
                            candidate
                            for candidate in controls
                            if candidate["role"] == "CheckBox"
                            and candidate["name"] == name
                        ),
                        None,
                    )
                    key = f"{name}:{color}"
                    if item is None or window is None:
                        passed = False
                        indicator_color_pixels[key] = 0
                        notes.append(f"control indicator color target is unavailable: {key}")
                        continue
                    count = _control_indicator_color_pixels(pixels, item, window, color)
                    indicator_color_pixels[key] = count
                    if count < minimum:
                        passed = False
                        notes.append(
                            f"control indicator color {key} has {count} pixels; "
                            f"minimum is {minimum}"
                        )
            if case.required_text_metrics:
                text_metric_values = {}
                for name, color, minimum_height in case.required_text_metrics:
                    item = next(
                        (
                            candidate
                            for candidate in items
                            if candidate["role"] == "StaticText"
                            and candidate["name"] == name
                            and not candidate["invisible"]
                        ),
                        None,
                    )
                    key = f"{name}:{color}"
                    if item is None or window is None:
                        passed = False
                        text_metric_values[key] = {
                            "height": 0.0,
                            "color_distance": float("inf"),
                        }
                        notes.append(f"text metric target is unavailable: {key}")
                        continue
                    height = float(item["rect"][3])
                    distance = _control_color_distance(pixels, item, window, color)
                    text_metric_values[key] = {
                        "height": height,
                        "color_distance": distance,
                    }
                    if height < minimum_height:
                        passed = False
                        notes.append(
                            f"text metric {key} has height {height:g}; "
                            f"minimum is {minimum_height}"
                        )
                    if distance > 24.0:
                        passed = False
                        notes.append(
                            f"text metric {key} has pixel distance {distance:.1f}; "
                            "limit is 24"
                        )
            if case.required_single_line_control_names:
                control_text_vertical_spans = {}
                for name in case.required_single_line_control_names:
                    item = next(
                        (
                            candidate
                            for candidate in controls
                            if candidate["role"] == "CheckBox"
                            and candidate["name"] == name
                        ),
                        None,
                    )
                    if item is None or window is None:
                        passed = False
                        control_text_vertical_spans[name] = float("inf")
                        notes.append(f"single-line control target is unavailable: {name}")
                        continue
                    span = _control_text_vertical_span(pixels, item, window)
                    control_text_vertical_spans[name] = span
                    if span > 22.0:
                        passed = False
                        notes.append(
                            f"control text {name} spans {span:.1f}px vertically; "
                            "single-line limit is 22"
                        )
            for expected_checked, names in (
                (True, case.required_checked_names),
                (False, case.required_unchecked_names),
            ):
                for name in names:
                    item = next(
                        (
                            candidate
                            for candidate in controls
                            if candidate["role"] == "CheckBox"
                            and candidate["name"] == name
                        ),
                        None,
                    )
                    if item is None:
                        passed = False
                        notes.append(f"checkbox state target is unavailable: {name}")
                    elif bool(item.get("checked")) is not expected_checked:
                        passed = False
                        state = "checked" if expected_checked else "unchecked"
                        notes.append(f"checkbox is not {state}: {name}")
            for name in case.required_accessible_names:
                if name not in visible_by_name:
                    passed = False
                    notes.append(f"required accessible item is missing: {name}")
            for name in case.required_in_window_names:
                candidates = [
                    item
                    for item in items
                    if item["name"] == name and not item["invisible"]
                ]
                inside = False
                if window is not None:
                    left, top, window_width, window_height = window["rect"]
                    right = left + window_width
                    bottom = top + window_height
                    inside = any(
                        item["rect"][0] >= left
                        and item["rect"][1] >= top
                        and item["rect"][0] + item["rect"][2] <= right
                        and item["rect"][1] + item["rect"][3] <= bottom
                        for item in candidates
                    )
                if not inside:
                    passed = False
                    notes.append(f"required item is outside the first window: {name}")
            for first_name, second_name in case.required_non_overlapping_pairs:
                first = visible_by_name.get(first_name)
                second = visible_by_name.get(second_name)
                separated = False
                if first is not None and second is not None:
                    first_x, first_y, first_width, first_height = first["rect"]
                    second_x, second_y, second_width, second_height = second["rect"]
                    separated = (
                        first_x + first_width <= second_x
                        or second_x + second_width <= first_x
                        or first_y + first_height <= second_y
                        or second_y + second_height <= first_y
                    )
                if not separated:
                    passed = False
                    notes.append(
                        "required items overlap or are unavailable: "
                        f"{first_name} <-> {second_name}"
                    )
            for child_name, container_name in case.required_contained_pairs:
                children = [
                    item
                    for item in items
                    if item["name"] == child_name
                    and not item["invisible"]
                ]
                containers = [
                    item
                    for item in items
                    if item["name"] == container_name and not item["invisible"]
                ]
                contained = any(
                    child["rect"][0] >= container["rect"][0]
                    and child["rect"][1] >= container["rect"][1]
                    and child["rect"][0] + child["rect"][2]
                    <= container["rect"][0] + container["rect"][2]
                    and child["rect"][1] + child["rect"][3]
                    <= container["rect"][1] + container["rect"][3]
                    for child in children
                    for container in containers
                )
                if not contained:
                    passed = False
                    notes.append(
                        "required item is not fully inside its container: "
                        f"{child_name} <-> {container_name}"
                    )
            for context_name, control_name in case.required_context_above_pairs:
                context = visible_by_name.get(context_name)
                control = visible_by_name.get(control_name)
                separated = False
                if context is not None and control is not None and window is not None:
                    content_floor = window["rect"][1] + 68
                    context_top = context["rect"][1]
                    context_bottom = context["rect"][1] + context["rect"][3]
                    control_top = control["rect"][1]
                    separated = (
                        context_top >= content_floor and context_bottom <= control_top
                    )
                if not separated:
                    passed = False
                    notes.append(
                        "context is clipped or overlapped by its control: "
                        f"{context_name} -> {control_name}"
                    )
            for name in case.required_descriptions:
                item = visible_by_name.get(name)
                if item is None or not item["description"].strip():
                    passed = False
                    notes.append(f"required accessible description is missing: {name}")
            visible_descriptions = [
                item["description"] for item in items if not item["invisible"]
            ]
            for text in case.required_description_texts:
                if not any(text in description for description in visible_descriptions):
                    passed = False
                    notes.append(f"required accessible description text is missing: {text}")
            for name in case.required_enabled_names:
                item = visible_by_name.get(name)
                if item is None or item["disabled"]:
                    passed = False
                    notes.append(f"required control is not enabled: {name}")
            for name in case.required_disabled_names:
                item = visible_by_name.get(name)
                if item is None or not item["disabled"]:
                    passed = False
                    notes.append(f"required control is not disabled: {name}")
            for name in case.required_nonfocusable_names:
                item = visible_by_name.get(name)
                if item is None or item["focusable"]:
                    passed = False
                    notes.append(f"read-only status is unexpectedly focusable: {name}")
            for name in case.forbidden_accessible_names:
                if name in visible_by_name:
                    passed = False
                    notes.append(f"forbidden accessible item remains visible: {name}")
    focus_names = None
    if trace_focus:
        if not focus_trace_path.is_file():
            passed = False
            notes.append("keyboard focus trace is missing")
        else:
            focus_trace = json.loads(focus_trace_path.read_text(encoding="utf-8"))
            focus_names = [item["name"] for item in focus_trace]
            def outside_window(item: dict[str, object]) -> bool:
                x, y, width, height = item["rect"]
                window_x, window_y, window_width, window_height = item.get(
                    "window_rect", [0, 0, 0, 0]
                )
                return (
                    x < window_x
                    or x + width > window_x + window_width
                    or y + height > window_y + window_height
                )

            invalid_focus = [
                item
                for item in focus_trace
                if not item["name"].strip()
                or item["role"]
                not in {"Button", "Slider", "CheckBox", "ComboBox", "EditableText", "Graphic"}
                or item["rect"][2] <= 0
                or item["rect"][3] <= 0
                or outside_window(item)
            ]
            if invalid_focus:
                passed = False
                notes.append(
                    f"{len(invalid_focus)} keyboard focus step(s) are hidden, dead, or outside the window"
                )
            if case.expected_focus_names and focus_names != list(case.expected_focus_names):
                passed = False
                notes.append(
                    "focus order differs: expected "
                    + " → ".join(case.expected_focus_names)
                    + "; found "
                    + " → ".join(focus_names)
                )
    transport_trace = None
    rss_growth_kb = None
    prediction_text_layout = None
    observation_text_layout = None
    prediction_layout_required = any(
        value is not None
        for value in (
            case.maximum_prediction_horizontal_overflow,
            case.minimum_prediction_vertical_overflow,
            case.maximum_prediction_vertical_overflow,
            case.minimum_prediction_line_count,
            case.maximum_prediction_line_count,
            case.expected_prediction_vertical_scrollbar,
            case.minimum_prediction_scroll_position,
            case.maximum_prediction_scroll_position,
            case.minimum_prediction_peak_scroll_position,
            case.expected_prediction_input_length,
        )
    )
    observation_layout_required = any(
        value is not None
        for value in (
            case.maximum_observation_horizontal_overflow,
            case.minimum_observation_vertical_overflow,
            case.maximum_observation_vertical_overflow,
            case.minimum_observation_line_count,
            case.maximum_observation_line_count,
            case.expected_observation_vertical_scrollbar,
            case.minimum_observation_scroll_position,
            case.maximum_observation_scroll_position,
            case.minimum_observation_peak_scroll_position,
            case.expected_observation_input_length,
        )
    )
    if case.required_now_prompt_fragments and "record_backend" not in actions:
        passed = False
        notes.append("now prompt validation has no backend trace action")
    if prediction_layout_required and "record_backend" not in actions:
        passed = False
        notes.append("prediction layout validation has no backend trace action")
    if observation_layout_required and "record_backend" not in actions:
        passed = False
        notes.append("observation layout validation has no backend trace action")
    if case.expected_saved_prediction_length is not None and "record_backend" not in actions:
        passed = False
        notes.append("saved prediction validation has no backend trace action")
    if case.expected_saved_observation_length is not None and "record_backend" not in actions:
        passed = False
        notes.append("saved observation validation has no backend trace action")
    if "record_backend" in actions:
        if not backend_trace_path.is_file():
            passed = False
            notes.append("transport state trace is missing")
        else:
            transport_trace = json.loads(backend_trace_path.read_text(encoding="utf-8"))
            actual_speeds = [float(item["session_speed"]) for item in transport_trace]
            actual_states = [str(item["session_state"]) for item in transport_trace]
            actual_pages = [str(item.get("page", "")) for item in transport_trace]
            actual_active = [
                bool(item.get("has_active_experiment")) for item in transport_trace
            ]
            actual_batch_probe = [
                bool(item.get("batch_probe_started")) for item in transport_trace
            ]
            speed_labels = {0.25: "0.25×", 0.5: "0.5×", 1.0: "1×", 2.0: "2×"}
            mismatched = [
                item
                for item in transport_trace
                if item["session_speed"] is None
                or item["ui_speed_text"]
                != speed_labels.get(float(item["session_speed"]), "")
            ]
            if mismatched:
                passed = False
                notes.append(f"{len(mismatched)} UI/backend playback speed mismatch(es)")
            if case.expected_speed_trace and actual_speeds != list(case.expected_speed_trace):
                passed = False
                notes.append(f"expected speed trace {case.expected_speed_trace}, found {actual_speeds}")
            if case.expected_transport_states and actual_states != list(
                case.expected_transport_states
            ):
                passed = False
                notes.append(
                    f"expected transport states {case.expected_transport_states}, found {actual_states}"
                )
            if case.expected_pages and actual_pages != list(case.expected_pages):
                passed = False
                notes.append(f"expected page trace {case.expected_pages}, found {actual_pages}")
            if prediction_layout_required:
                sample = transport_trace[-1]
                content_width = float(sample.get("prediction_content_width") or 0.0)
                available_width = float(sample.get("prediction_available_width") or 0.0)
                content_height = float(sample.get("prediction_content_height") or 0.0)
                available_height = float(sample.get("prediction_available_height") or 0.0)
                line_count = int(sample.get("prediction_line_count") or 0)
                scroll_position = float(sample.get("prediction_scroll_position") or 0.0)
                scrollbar_visible = bool(sample.get("prediction_scrollbar_visible"))
                input_length = int(sample.get("prediction_input_length") or 0)
                prediction_text_layout = {
                    "horizontal_overflow": max(0.0, content_width - available_width),
                    "vertical_overflow": max(0.0, content_height - available_height),
                    "line_count": float(line_count),
                    "scroll_position": scroll_position,
                    "scrollbar_visible": scrollbar_visible,
                    "input_length": float(input_length),
                }
                limits = (
                    ("horizontal_overflow", case.maximum_prediction_horizontal_overflow),
                    ("vertical_overflow", case.maximum_prediction_vertical_overflow),
                )
                for metric, maximum in limits:
                    if maximum is not None and prediction_text_layout[metric] > maximum:
                        passed = False
                        notes.append(
                            f"prediction {metric} is {prediction_text_layout[metric]:.1f}px; "
                            f"maximum is {maximum:.1f}px"
                        )
                if (
                    case.minimum_prediction_vertical_overflow is not None
                    and prediction_text_layout["vertical_overflow"]
                    < case.minimum_prediction_vertical_overflow
                ):
                    passed = False
                    notes.append(
                        "prediction vertical overflow is "
                        f"{prediction_text_layout['vertical_overflow']:.1f}px; minimum is "
                        f"{case.minimum_prediction_vertical_overflow:.1f}px"
                    )
                if (
                    case.minimum_prediction_line_count is not None
                    and line_count < case.minimum_prediction_line_count
                ):
                    passed = False
                    notes.append(
                        f"prediction uses {line_count} line(s); minimum is "
                        f"{case.minimum_prediction_line_count}"
                    )
                if (
                    case.maximum_prediction_line_count is not None
                    and line_count > case.maximum_prediction_line_count
                ):
                    passed = False
                    notes.append(
                        f"prediction uses {line_count} line(s); maximum is "
                        f"{case.maximum_prediction_line_count}"
                    )
                if (
                    case.expected_prediction_vertical_scrollbar is not None
                    and scrollbar_visible
                    != case.expected_prediction_vertical_scrollbar
                ):
                    passed = False
                    notes.append(
                        "prediction vertical scrollbar visibility is "
                        f"{scrollbar_visible}; expected "
                        f"{case.expected_prediction_vertical_scrollbar}"
                    )
                if (
                    case.minimum_prediction_scroll_position is not None
                    and scroll_position < case.minimum_prediction_scroll_position
                ):
                    passed = False
                    notes.append(
                        f"prediction scroll position is {scroll_position:.1f}px; minimum is "
                        f"{case.minimum_prediction_scroll_position:.1f}px"
                    )
                if (
                    case.maximum_prediction_scroll_position is not None
                    and scroll_position > case.maximum_prediction_scroll_position
                ):
                    passed = False
                    notes.append(
                        f"prediction scroll position is {scroll_position:.1f}px; maximum is "
                        f"{case.maximum_prediction_scroll_position:.1f}px"
                    )
                if case.minimum_prediction_peak_scroll_position is not None:
                    peak_scroll_position = max(
                        float(item.get("prediction_scroll_position") or 0.0)
                        for item in transport_trace
                    )
                    if peak_scroll_position < case.minimum_prediction_peak_scroll_position:
                        passed = False
                        notes.append(
                            "prediction peak scroll position is "
                            f"{peak_scroll_position:.1f}px; minimum is "
                            f"{case.minimum_prediction_peak_scroll_position:.1f}px"
                        )
                if (
                    case.expected_prediction_input_length is not None
                    and input_length != case.expected_prediction_input_length
                ):
                    passed = False
                    notes.append(
                        f"prediction input length is {input_length}; expected "
                        f"{case.expected_prediction_input_length}"
                    )
            if observation_layout_required:
                sample = transport_trace[-1]
                content_width = float(sample.get("observation_content_width") or 0.0)
                available_width = float(sample.get("observation_available_width") or 0.0)
                content_height = float(sample.get("observation_content_height") or 0.0)
                available_height = float(sample.get("observation_available_height") or 0.0)
                line_count = int(sample.get("observation_line_count") or 0)
                scroll_position = float(sample.get("observation_scroll_position") or 0.0)
                scrollbar_visible = bool(sample.get("observation_scrollbar_visible"))
                input_length = int(sample.get("observation_input_length") or 0)
                observation_text_layout = {
                    "horizontal_overflow": max(0.0, content_width - available_width),
                    "vertical_overflow": max(0.0, content_height - available_height),
                    "line_count": float(line_count),
                    "scroll_position": scroll_position,
                    "scrollbar_visible": scrollbar_visible,
                    "input_length": float(input_length),
                }
                limits = (
                    (
                        "horizontal_overflow",
                        case.maximum_observation_horizontal_overflow,
                    ),
                    ("vertical_overflow", case.maximum_observation_vertical_overflow),
                )
                for metric, maximum in limits:
                    if maximum is not None and observation_text_layout[metric] > maximum:
                        passed = False
                        notes.append(
                            f"observation {metric} is "
                            f"{observation_text_layout[metric]:.1f}px; maximum is "
                            f"{maximum:.1f}px"
                        )
                if (
                    case.minimum_observation_vertical_overflow is not None
                    and observation_text_layout["vertical_overflow"]
                    < case.minimum_observation_vertical_overflow
                ):
                    passed = False
                    notes.append(
                        "observation vertical overflow is "
                        f"{observation_text_layout['vertical_overflow']:.1f}px; minimum is "
                        f"{case.minimum_observation_vertical_overflow:.1f}px"
                    )
                if (
                    case.minimum_observation_line_count is not None
                    and line_count < case.minimum_observation_line_count
                ):
                    passed = False
                    notes.append(
                        f"observation uses {line_count} line(s); minimum is "
                        f"{case.minimum_observation_line_count}"
                    )
                if (
                    case.maximum_observation_line_count is not None
                    and line_count > case.maximum_observation_line_count
                ):
                    passed = False
                    notes.append(
                        f"observation uses {line_count} line(s); maximum is "
                        f"{case.maximum_observation_line_count}"
                    )
                if (
                    case.expected_observation_vertical_scrollbar is not None
                    and scrollbar_visible
                    != case.expected_observation_vertical_scrollbar
                ):
                    passed = False
                    notes.append(
                        "observation vertical scrollbar visibility is "
                        f"{scrollbar_visible}; expected "
                        f"{case.expected_observation_vertical_scrollbar}"
                    )
                if (
                    case.minimum_observation_scroll_position is not None
                    and scroll_position < case.minimum_observation_scroll_position
                ):
                    passed = False
                    notes.append(
                        f"observation scroll position is {scroll_position:.1f}px; minimum is "
                        f"{case.minimum_observation_scroll_position:.1f}px"
                    )
                if (
                    case.maximum_observation_scroll_position is not None
                    and scroll_position > case.maximum_observation_scroll_position
                ):
                    passed = False
                    notes.append(
                        f"observation scroll position is {scroll_position:.1f}px; maximum is "
                        f"{case.maximum_observation_scroll_position:.1f}px"
                    )
                if case.minimum_observation_peak_scroll_position is not None:
                    peak_scroll_position = max(
                        float(item.get("observation_scroll_position") or 0.0)
                        for item in transport_trace
                    )
                    if peak_scroll_position < case.minimum_observation_peak_scroll_position:
                        passed = False
                        notes.append(
                            "observation peak scroll position is "
                            f"{peak_scroll_position:.1f}px; minimum is "
                            f"{case.minimum_observation_peak_scroll_position:.1f}px"
                        )
                if (
                    case.expected_observation_input_length is not None
                    and input_length != case.expected_observation_input_length
                ):
                    passed = False
                    notes.append(
                        f"observation input length is {input_length}; expected "
                        f"{case.expected_observation_input_length}"
                    )
            if case.expected_active_trace and actual_active != list(
                case.expected_active_trace
            ):
                passed = False
                notes.append(
                    f"expected active-session trace {case.expected_active_trace}, "
                    f"found {actual_active}"
                )
            if case.expected_batch_probe_trace and actual_batch_probe != list(
                case.expected_batch_probe_trace
            ):
                passed = False
                notes.append(
                    f"expected batch-start probe {case.expected_batch_probe_trace}, "
                    f"found {actual_batch_probe}"
                )
            if case.require_camera_gesture_trace:
                if len(transport_trace) != 5:
                    passed = False
                    notes.append(
                        f"camera gesture trace has {len(transport_trace)} samples; expected 5"
                    )
                else:
                    first, orbit, pan, zoom, reset = transport_trace
                    orbit_changed = any(
                        abs(float(orbit[key]) - float(first[key])) > 1e-6
                        for key in ("camera_azimuth", "camera_elevation")
                    )
                    pan_changed = max(
                        abs(float(after) - float(before))
                        for before, after in zip(
                            orbit["camera_lookat"], pan["camera_lookat"], strict=True
                        )
                    ) > 1e-6
                    zoom_changed = (
                        abs(float(zoom["camera_distance"]) - float(pan["camera_distance"]))
                        > 1e-6
                    )
                    reset_values = (
                        "camera_azimuth",
                        "camera_elevation",
                        "camera_distance",
                    )
                    reset_restored = all(
                        abs(float(reset[key]) - float(first[key])) <= 1e-6
                        for key in reset_values
                    ) and all(
                        abs(float(after) - float(before)) <= 1e-6
                        for before, after in zip(
                            first["camera_lookat"], reset["camera_lookat"], strict=True
                        )
                    )
                    if (
                        not orbit_changed
                        or not pan_changed
                        or not zoom_changed
                        or not reset_restored
                    ):
                        passed = False
                        notes.append(
                            "camera gestures/reset did not change and restore independently: "
                            f"{orbit_changed}/{pan_changed}/{zoom_changed}/{reset_restored}"
                        )
            for first, second in case.stable_time_trace_pairs:
                if first >= len(transport_trace) or second >= len(transport_trace):
                    passed = False
                    notes.append(f"missing stable-time trace pair {(first, second)}")
                    continue
                first_time = float(transport_trace[first].get("session_time", -1.0))
                second_time = float(transport_trace[second].get("session_time", -1.0))
                if abs(second_time - first_time) > 1e-9:
                    passed = False
                    notes.append(
                        f"background time changed for trace pair {(first, second)}: "
                        f"{first_time} -> {second_time}"
                    )
            if case.expected_cleanup_trace:
                session_cleanup = [bool(item["previous_session_closed"]) for item in transport_trace]
                adapter_cleanup = [bool(item["previous_adapter_closed"]) for item in transport_trace]
                expected_cleanup = list(case.expected_cleanup_trace)
                if session_cleanup != expected_cleanup or adapter_cleanup != expected_cleanup:
                    passed = False
                    notes.append(
                        "session/adapter cleanup differs: expected "
                        f"{expected_cleanup}, found {session_cleanup}/{adapter_cleanup}"
                    )
            if case.cleanup_cycle_size:
                size = case.cleanup_cycle_size
                session_cleanup = [bool(item["previous_session_closed"]) for item in transport_trace]
                adapter_cleanup = [bool(item["previous_adapter_closed"]) for item in transport_trace]
                groups = [
                    (session_cleanup[index : index + size], adapter_cleanup[index : index + size])
                    for index in range(0, len(transport_trace), size)
                ]
                invalid = [
                    group
                    for group in groups
                    if len(group[0]) != size or not group[0][-1] or not group[1][-1]
                ]
                if invalid:
                    passed = False
                    notes.append(f"{len(invalid)} cleanup cycle(s) did not release final resources")
            if case.expect_no_session_replacement:
                session_ids = {item["session_id"] for item in transport_trace}
                previous_ids = {item["previous_session_id"] for item in transport_trace}
                if len(session_ids) != 1 or session_ids != previous_ids:
                    passed = False
                    notes.append("a guarded duplicate launch replaced the active session")
            if case.maximum_rss_growth_kb is not None:
                rss_values = [
                    item["rss_kb"]
                    for item in transport_trace[case.rss_ignore_initial_samples :]
                ]
                if len(rss_values) < 2:
                    passed = False
                    notes.append("resident-memory audit has fewer than two post-warm-up samples")
                if any(value is None for value in rss_values):
                    passed = False
                    notes.append("resident-memory measurement is unavailable")
                elif len(rss_values) >= 2:
                    rss_growth_kb = int(max(rss_values) - min(rss_values))
                    if rss_growth_kb > case.maximum_rss_growth_kb:
                        passed = False
                        notes.append(
                            f"resident memory grew {rss_growth_kb} KB; "
                            f"limit is {case.maximum_rss_growth_kb} KB"
                        )
            if case.required_now_prompt_fragments:
                prompt_sample = transport_trace[-1]
                prompt = str(prompt_sample.get("now_prompt", ""))
                missing_fragments = [
                    fragment for fragment in case.required_now_prompt_fragments if fragment not in prompt
                ]
                if missing_fragments:
                    passed = False
                    notes.append(f"now prompt is missing actionable text: {missing_fragments}")
                if case.require_untruncated_now_prompt and prompt_sample.get(
                    "now_prompt_truncated"
                ):
                    passed = False
                    notes.append("compact now prompt is visually truncated")
                line_count = prompt_sample.get("now_prompt_line_count")
                if case.maximum_now_prompt_lines is not None and (
                    line_count is None or int(line_count) > case.maximum_now_prompt_lines
                ):
                    passed = False
                    notes.append(
                        f"now prompt uses {line_count} lines; limit is {case.maximum_now_prompt_lines}"
                    )
            if case.expected_evidence_trace:
                evidence_trace = [
                    (
                        bool(item.get("has_prediction")),
                        bool(item.get("has_learner_action")),
                        bool(item.get("has_observation")),
                        int(item.get("active_stage", -1)),
                    )
                    for item in transport_trace
                ]
                if evidence_trace != list(case.expected_evidence_trace):
                    passed = False
                    notes.append(
                        f"expected evidence trace {case.expected_evidence_trace}, "
                        f"found {evidence_trace}"
                    )
            if case.expected_saved_prediction_length is not None:
                saved_length = int(
                    transport_trace[-1].get("prediction_saved_length") or 0
                )
                if saved_length != case.expected_saved_prediction_length:
                    passed = False
                    notes.append(
                        f"saved prediction length is {saved_length}; expected "
                        f"{case.expected_saved_prediction_length}"
                    )
            if case.expected_saved_observation_length is not None:
                saved_length = int(
                    transport_trace[-1].get("observation_saved_length") or 0
                )
                if saved_length != case.expected_saved_observation_length:
                    passed = False
                    notes.append(
                        f"saved observation length is {saved_length}; expected "
                        f"{case.expected_saved_observation_length}"
                    )
            for index in case.zero_time_trace_indices:
                if index >= len(transport_trace):
                    passed = False
                    notes.append(f"missing zero-time trace index {index}")
                    continue
                measured = float(transport_trace[index].get("session_time", -1.0))
                if abs(measured) > 1e-9:
                    passed = False
                    notes.append(f"trace {index} consumed physics before prediction/reset: {measured}")
            for index in case.positive_time_trace_indices:
                if index >= len(transport_trace):
                    passed = False
                    notes.append(f"missing started-time trace index {index}")
                    continue
                measured = float(transport_trace[index].get("session_time", 0.0))
                if measured <= 0.0:
                    passed = False
                    notes.append(f"trace {index} did not start physics after prediction: {measured}")
    if case.require_evidence_artifact:
        events_path = run_output / "interaction_events.json"
        if not events_path.is_file():
            passed = False
            notes.append("saved interaction evidence is missing")
        else:
            events = json.loads(events_path.read_text(encoding="utf-8"))
            markers = [
                event
                for event in events
                if event.get("kind") == "marker" and event.get("name") == "observation"
            ]
            value = markers[-1].get("value", {}) if markers else {}
            if not markers or not all(
                str(value.get(key, "")).strip() for key in ("prediction", "outcome", "note")
            ):
                passed = False
                notes.append("observation marker lacks prediction, outcome, or note")
    if case.required_interaction_event_names:
        events_path = run_output / "interaction_events.json"
        if not events_path.is_file():
            passed = False
            notes.append("saved interaction event log is missing")
        else:
            events = json.loads(events_path.read_text(encoding="utf-8"))
            actual_names = {str(event.get("name", "")) for event in events}
            missing_names = [
                name for name in case.required_interaction_event_names if name not in actual_names
            ]
            if missing_names:
                passed = False
                notes.append(f"saved interaction event names are missing: {missing_names}")
    if case.required_report_texts:
        report_path = run_output / "report.html"
        report = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
        for text_value in case.required_report_texts:
            if text_value not in report:
                passed = False
                notes.append(f"saved report is missing evidence text: {text_value}")
    stderr = completed.stderr.strip()
    if stderr:
        notes.append(stderr.splitlines()[-1][:180])
    return AuditResult(
        case.name,
        passed,
        completed.returncode,
        str(screenshot),
        dimensions,
        pure_black,
        viewport_run,
        focus_yellow_pixels,
        warning_amber_pixels,
        task_action_count,
        accessible_controls,
        unnamed_controls,
        scenario_start_buttons,
        scene_token_distance,
        notes,
        undersized_targets,
        focus_names,
        transport_trace,
        rss_growth_kb,
        primary_actions,
        primary_action_names,
        tour_connector_pixels,
        scenario_context_titles,
        control_color_distance,
        control_color_pixels,
        control_border_color_distance,
        role_border_color_pixels,
        indicator_color_pixels,
        text_metric_values,
        control_text_vertical_spans,
        scene_token_pixels,
        robot_foreground_pixels,
        prediction_text_layout,
        observation_text_layout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/mclab-ui-audit"))
    parser.add_argument("--with-gl", action="store_true", help="Also exercise threaded EGL rendering")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="GLOB",
        help="Run only matching case names; repeat for multiple glob patterns.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mclab-ui-settings-") as tmp:
        gl_cases = (
            GL_CASE,
            GL_CAMERA_GESTURE_CASE,
            GL_CAMERA_KEYBOARD_CASE,
            GL_CONTROL_PRECISION_CASE,
            GL_CORE_CONTROLS_CASE,
            GL_REPLAY_CASE,
            GL_RESTART_CASE,
            GL_CROSS_SCENARIO_CASE,
            GL_REPLAY_RESTART_CASE,
            GL_RESULTS_RECOVERY_CASE,
            GL_SCROLL_FOCUS_CASE,
            GL_RESULTS_LOAD_FOCUS_CASE,
            GL_EVIDENCE_HANDOFF_CASE,
        )
        cases = CASES + (gl_cases if args.with_gl else ())
        if args.case:
            cases = tuple(
                case
                for case in cases
                if any(fnmatch.fnmatchcase(case.name, pattern) for pattern in args.case)
            )
        if not cases:
            parser.error("No UI audit cases matched --case.")
        results = [_run_case(case, args.output, Path(tmp)) for case in cases]
    report = {"passed": all(item.passed for item in results), "cases": [asdict(item) for item in results]}
    report_path = args.output / "ui_audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in results:
        accessibility = (
            f"; controls={item.accessible_controls}; unnamed={item.unnamed_controls}; "
            f"undersized={item.undersized_targets}"
            if item.accessible_controls is not None
            else ""
        )
        focus = (
            f"; focus-yellow={item.focus_yellow_pixels}"
            if item.focus_yellow_pixels is not None
            else ""
        )
        warning = (
            f"; warning-amber={item.warning_amber_pixels}"
            if item.warning_amber_pixels is not None
            else ""
        )
        task = (
            f"; task-actions={item.task_action_count}"
            if item.task_action_count is not None
            else ""
        )
        tokens = (
            f"; tokens={item.scene_token_distance}"
            if item.scene_token_distance is not None
            else ""
        )
        memory = f"; rss-growth={item.rss_growth_kb}KB" if item.rss_growth_kb is not None else ""
        hierarchy = (
            f"; primary-actions={item.primary_actions}:{item.primary_action_names}"
            if item.primary_actions is not None
            else ""
        )
        tour = (
            f"; tour-connectors={item.tour_connector_pixels}"
            if item.tour_connector_pixels is not None
            else ""
        )
        scenario_titles = (
            f"; scenario-titles={item.scenario_context_titles}"
            if item.scenario_context_titles is not None
            else ""
        )
        control_colors = (
            f"; control-colors={item.control_color_distance}"
            if item.control_color_distance is not None
            else ""
        )
        control_pixels = (
            f"; control-pixels={item.control_color_pixels}"
            if item.control_color_pixels is not None
            else ""
        )
        control_border_colors = (
            f"; control-border-colors={item.control_border_color_distance}"
            if item.control_border_color_distance is not None
            else ""
        )
        role_border_pixels = (
            f"; role-border-pixels={item.role_border_color_pixels}"
            if item.role_border_color_pixels is not None
            else ""
        )
        indicator_colors = (
            f"; indicator-colors={item.indicator_color_pixels}"
            if item.indicator_color_pixels is not None
            else ""
        )
        text_metrics = (
            f"; text-metrics={item.text_metric_values}"
            if item.text_metric_values is not None
            else ""
        )
        control_text_spans = (
            f"; control-text-spans={item.control_text_vertical_spans}"
            if item.control_text_vertical_spans is not None
            else ""
        )
        scene_pixels = (
            f"; scene-pixels={item.scene_token_pixels}"
            if item.scene_token_pixels is not None
            else ""
        )
        robot_pixels = (
            f"; robot-pixels={item.robot_foreground_pixels}"
            if item.robot_foreground_pixels is not None
            else ""
        )
        prediction_layout = (
            f"; prediction-layout={item.prediction_text_layout}"
            if item.prediction_text_layout is not None
            else ""
        )
        observation_layout = (
            f"; observation-layout={item.observation_text_layout}"
            if item.observation_text_layout is not None
            else ""
        )
        print(
            f"{'PASS' if item.passed else 'FAIL'} {item.name}: "
            f"{item.dimensions}; viewport={item.viewport_dark_run}"
            f"{focus}{warning}{task}{accessibility}{tokens}{memory}{hierarchy}{tour}"
            f"{scenario_titles}{control_colors}{control_pixels}"
            f"{control_border_colors}"
            f"{role_border_pixels}"
            f"{indicator_colors}"
            f"{text_metrics}"
            f"{control_text_spans}"
            f"{scene_pixels}"
            f"{robot_pixels}"
            f"{prediction_layout}"
            f"{observation_layout}"
        )
    print(f"Report: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
