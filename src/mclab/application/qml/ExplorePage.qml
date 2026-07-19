import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var scenarioItems: backend.scenarios
    property var activeTerms: search.text.trim().length === 0
                              ? [] : search.text.trim().toLowerCase().split(/\s+/)
    ScrollFocusHelper { id: scenarioFocusScroll }

    function matches(scenario) {
        var searchable = ((scenario.title || "") + " " + (scenario.purpose || "") + " "
                          + (scenario.lab || "") + " " + (scenario.id || "")).toLowerCase()
        var queryMatches = true
        for (var termIndex = 0; termIndex < activeTerms.length; ++termIndex) {
            if (searchable.indexOf(activeTerms[termIndex]) < 0) {
                queryMatches = false
                break
            }
        }
        var levelIds = ["", "intro", "build", "deep-dive"]
        var levelMatches = levelFilter.currentIndex === 0
                           || scenario.difficultyId === levelIds[levelFilter.currentIndex]
        var modeMatches = modeFilter.currentIndex === 0
                          || (modeFilter.currentIndex === 1 && scenario.requiresEvidence)
                          || (modeFilter.currentIndex === 2 && !scenario.requiresEvidence)
        return queryMatches && levelMatches && modeMatches
    }

    function filteredCount() {
        var count = 0
        for (var index = 0; index < scenarioItems.length; ++index) {
            if (matches(scenarioItems[index]))
                ++count
        }
        return count
    }

    function resetFilters() {
        search.clear()
        levelFilter.currentIndex = 0
        modeFilter.currentIndex = 0
        search.forceActiveFocus()
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Label {
                text: backend.localizedText(backend.language, "nav.explore")
                color: "#172033"
                font.pixelSize: 30
                font.bold: true
                Layout.fillWidth: true
            }
            Label {
                id: resultCount
                text: backend.localizedText(backend.language, "explore.result_count")
                      .replace("{shown}", page.filteredCount())
                      .replace("{total}", page.scenarioItems.length)
                color: "#334155"
                font.pixelSize: 14
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }
        }
        ActiveSessionBar {}
        BatchSessionBar {}
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            TextField {
                id: search
                objectName: "scenarioSearch"
                Layout.fillWidth: true
                Layout.minimumWidth: 160
                implicitHeight: 48
                placeholderText: backend.localizedText(backend.language,
                                                         "explore.search_placeholder")
                placeholderTextColor: "#5B6475"
                color: "#172033"
                font.pixelSize: 14
                leftPadding: 12
                rightPadding: 12
                verticalAlignment: TextInput.AlignVCenter
                Accessible.name: backend.localizedText(backend.language, "explore.search")
                Accessible.description: backend.localizedText(backend.language,
                                                               "explore.search_help")
                background: Rectangle {
                    color: "#FFFFFF"
                    radius: 8
                    border.color: "#64748B"
                    border.width: 2
                }
                FocusRing { anchors.fill: parent; shown: search.activeFocus }
            }
            FilterCombo {
                id: levelFilter
                objectName: "scenarioLevelFilter"
                model: [
                    backend.localizedText(backend.language, "explore.filter_all"),
                    backend.localizedText(backend.language, "difficulty.intro"),
                    backend.localizedText(backend.language, "difficulty.build"),
                    backend.localizedText(backend.language, "difficulty.deep-dive")
                ]
                filterName: backend.localizedText(backend.language, "explore.level_filter")
                displayPrefix: backend.localizedText(backend.language, "explore.level_short")
                filterDescription: backend.localizedText(backend.language,
                                                          "explore.level_filter_help")
            }
            FilterCombo {
                id: modeFilter
                objectName: "scenarioModeFilter"
                model: [
                    backend.localizedText(backend.language, "explore.filter_all"),
                    backend.localizedText(backend.language, "explore.filter_hands_on"),
                    backend.localizedText(backend.language, "explore.filter_automatic")
                ]
                filterName: backend.localizedText(backend.language, "explore.mode_filter")
                displayPrefix: backend.localizedText(backend.language, "explore.mode_short")
                filterDescription: backend.localizedText(backend.language,
                                                          "explore.mode_filter_help")
            }
        }
        ScrollView {
            id: scenarioScroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            GridLayout {
                id: scenarioGrid
                width: parent.width
                columns: width >= 1500 ? 3 : width >= 900 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 12
                Rectangle {
                    visible: page.filteredCount() === 0
                    Layout.fillWidth: true
                    Layout.columnSpan: scenarioGrid.columns
                    Layout.preferredHeight: 138
                    radius: 12
                    color: "#FFFFFF"
                    border.color: "#DCE2EC"
                    border.width: 1
                    ColumnLayout {
                        anchors.centerIn: parent
                        width: Math.min(parent.width - 32, 520)
                        spacing: 8
                        Label {
                            text: backend.localizedText(backend.language, "explore.empty_title")
                            color: "#172033"
                            font.pixelSize: 18
                            font.bold: true
                            Layout.alignment: Qt.AlignHCenter
                        }
                        Label {
                            text: backend.localizedText(backend.language, "explore.empty_detail")
                            color: "#475569"
                            font.pixelSize: 14
                            wrapMode: Text.WordWrap
                            horizontalAlignment: Text.AlignHCenter
                            Layout.fillWidth: true
                        }
                        MButton {
                            id: clearFilters
                            objectName: "clearExploreFilters"
                            text: backend.localizedText(backend.language, "explore.clear_filters")
                            accessibleDescription: backend.localizedText(
                                                       backend.language,
                                                       "explore.clear_filters_help")
                            Layout.alignment: Qt.AlignHCenter
                            onClicked: page.resetFilters()
                        }
                    }
                }
                Repeater {
                    model: page.scenarioItems
                    ScenarioCard {
                        Layout.fillWidth: true
                        scenario: modelData
                        launchBlocked: backend.hasActiveExperiment || backend.batchProgress.running
                        launchBlockedDescription: backend.batchProgress.running
                                                  ? backend.localizedText(backend.language,
                                                                          "batch.launch_blocked")
                                                  : backend.localizedText(backend.language,
                                                                          "active.launch_blocked")
                        visible: page.matches(modelData)
                        onStartRequested: id => backend.startScenario(id)
                        onFocusRevealRequested: control =>
                            scenarioFocusScroll.reveal(scenarioScroller, scenarioGrid, control)
                    }
                }
            }
        }
    }
}
