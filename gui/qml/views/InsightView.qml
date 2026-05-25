import QtQuick

import QtQuick.Controls

import QtQuick.Layouts

import "../components"

import ".."

import "insight"



Item {

    id: root



    function parseJson(s, fallback) {

        try { var v = JSON.parse(s || ""); return v !== null ? v : fallback } catch(e) { return fallback }

    }



    function personaCoverageLabel(p) {

        if (!p || !p.coverage) return ""

        var c = p.coverage

        return "분석 샘플 — Grok " + (c.grok || 0) + " · 캐논 " + (c.canonical || 0) + " · 자막 " + (c.subtitle || 0)

    }



    function reloadAllFromModel() {

        root.actors = root.parseJson(InsightModel.topActors, [])

        root.genres = root.parseJson(InsightModel.topGenres, [])

        root.makers = root.parseJson(InsightModel.topMakers, [])

        root.recs = root.parseJson(InsightModel.todayRecs, [])

        root.nextWatch = root.parseJson(InsightModel.nextWatchRecs, [])

        root.hiddenGems = root.parseJson(InsightModel.hiddenGems, [])

        root.actorCollections = root.parseJson(InsightModel.actorCollections, {actors:[]})

        root.tasteData = root.parseJson(InsightModel.tasteVector, {axes:[]})

        root.heatmapData = root.parseJson(InsightModel.watchHeatmap, {year: 2026, days:{}, max:0})

        root.persona = InsightModel.personaCardObject || {}

        root.pipeline = root.parseJson(InsightModel.pipelineReport, {})

        root.stats = root.parseJson(InsightModel.libraryStats, {})

        root.trend = root.parseJson(InsightModel.recentTrend, {actors:[], genres:[]})

        root.tasteDrift = root.parseJson(InsightModel.tasteDrift, {series:[]})

        root.libraryDist = root.parseJson(InsightModel.libraryDistribution, {actors:[], genres:[], makers:[]})

        root.weeklyDigest = root.parseJson(InsightModel.weeklyDigest, {lines: [], has_data: false})

    }



    property var actors:      parseJson(InsightModel.topActors,    [])

    property var genres:      parseJson(InsightModel.topGenres,    [])

    property var makers:      parseJson(InsightModel.topMakers,    [])

    property var recs:        parseJson(InsightModel.todayRecs,    [])

    property var nextWatch:   parseJson(InsightModel.nextWatchRecs, [])

    property var hiddenGems:  parseJson(InsightModel.hiddenGems, [])

    property var actorCollections: parseJson(InsightModel.actorCollections, {actors:[]})

    property var tasteData:   parseJson(InsightModel.tasteVector,  {axes:[]})

    property var heatmapData: parseJson(InsightModel.watchHeatmap, {year: 2026, days:{}, max:0})

    property var persona:     InsightModel.personaCardObject || {}

    property var pipeline:    parseJson(InsightModel.pipelineReport, {})

    property var stats:       parseJson(InsightModel.libraryStats, {})

    property var trend:       parseJson(InsightModel.recentTrend,  {actors:[], genres:[]})

    property var tasteDrift:  parseJson(InsightModel.tasteDrift, {series:[]})

    property var libraryDist: parseJson(InsightModel.libraryDistribution, {actors:[], genres:[], makers:[]})

    property var weeklyDigest: parseJson(InsightModel.weeklyDigest, {lines: [], has_data: false})



    property int insightTabIndex: 0

    property bool tabOverviewEver: true

    property bool tabTrendsEver: false

    property bool tabRecommendEver: false

    property bool tabCollectionEver: false



    onInsightTabIndexChanged: {

        if (insightTabIndex === 0) tabOverviewEver = true

        else if (insightTabIndex === 1) tabTrendsEver = true

        else if (insightTabIndex === 2) tabRecommendEver = true

        else if (insightTabIndex === 3) tabCollectionEver = true

        InsightModel.ensureTabData(insightTabIndex)

    }



    Component.onCompleted: reloadAllFromModel()



    Connections {

        target: InsightModel

        function onAllDataChanged() { root.reloadAllFromModel() }

        function onPersonaCardChanged() {

            root.persona = InsightModel.personaCardObject || {}

        }

    }



    ColumnLayout {

        anchors.fill: parent

        spacing: 0



        Rectangle {

            Layout.fillWidth: true

            height: 64

            color: "transparent"



            RowLayout {

                anchors.fill: parent

                anchors.leftMargin: Theme.spacingLg

                anchors.rightMargin: Theme.spacingLg

                spacing: Theme.spacingMd



                Text {

                    text: "📊"

                    font.pixelSize: 28

                    Layout.alignment: Qt.AlignVCenter

                }

                Text {

                    text: "나의 취향 인사이트"

                    font.pixelSize: Theme.fontTitle

                    font.weight: Font.ExtraBold

                    color: Theme.textPrimary

                    Layout.alignment: Qt.AlignVCenter

                }



                Item { Layout.fillWidth: true }



                ActionButton {

                    text: InsightModel.isBatchRunning ? "동기화 중…" : "취향 재분석"

                    primary: true

                    enabled: !InsightModel.isBatchRunning

                    height: 38

                    onClicked: InsightModel.runBatch()

                }



                ActionButton {

                    text: "새로고침"

                    primary: false

                    height: 38

                    onClicked: InsightModel.refresh()

                }

            }



            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.glassBorder }

        }



        Item {

            Layout.fillWidth: true

            Layout.leftMargin: Theme.spacingLg

            Layout.rightMargin: Theme.spacingLg

            Layout.topMargin: Theme.spacingSm

            Layout.preferredHeight: 44



            InsightTabBar {

                anchors.fill: parent

                currentIndex: root.insightTabIndex

                onTabActivated: function(idx) { root.insightTabIndex = idx }

            }

        }



        StackLayout {

            id: tabStack

            Layout.fillWidth: true

            Layout.fillHeight: true

            currentIndex: root.insightTabIndex



            Loader {

                active: root.tabOverviewEver

                Layout.fillWidth: true

                Layout.fillHeight: true

                sourceComponent: overviewTab

            }



            Loader {

                active: root.tabTrendsEver

                Layout.fillWidth: true

                Layout.fillHeight: true

                sourceComponent: trendsTab

            }



            Loader {

                active: root.tabRecommendEver

                Layout.fillWidth: true

                Layout.fillHeight: true

                sourceComponent: recommendTab

            }



            Loader {

                active: root.tabCollectionEver

                Layout.fillWidth: true

                Layout.fillHeight: true

                sourceComponent: collectionTab

            }

        }

    }



    Component {

        id: overviewTab

        AppScrollView {

            id: overviewScroll

            clip: true

            contentWidth: availableWidth

            ScrollBar.vertical.policy: ScrollBar.AsNeeded



            Column {

                width: parent.width - Theme.spacingLg * 2

                anchors.horizontalCenter: parent.horizontalCenter

                topPadding: Theme.spacingMd

                bottomPadding: Theme.spacingLg

                spacing: 0



                InsightTabOverview {

                    width: parent.width

                    height: Math.max(implicitHeight, overviewScroll.availableHeight - Theme.spacingMd - Theme.spacingLg)

                    weeklyDigest: root.weeklyDigest

                    stats: root.stats

                    tasteData: root.tasteData

                    persona: root.persona

                    personaCoverageLabel: root.personaCoverageLabel

                    viewportHeight: overviewScroll.availableHeight

                }

            }

        }

    }



    Component {

        id: trendsTab

        AppScrollView {

            clip: true

            contentWidth: availableWidth

            ScrollBar.vertical.policy: ScrollBar.AsNeeded



            Column {

                width: parent.width - Theme.spacingLg * 2

                anchors.horizontalCenter: parent.horizontalCenter

                topPadding: Theme.spacingMd

                bottomPadding: Theme.spacingLg



                InsightTabTrends {

                    width: parent.width

                    heatmapData: root.heatmapData

                    tasteDrift: root.tasteDrift

                    trend: root.trend

                }

            }

        }

    }



    Component {

        id: recommendTab

        AppScrollView {

            clip: true

            contentWidth: availableWidth

            ScrollBar.vertical.policy: ScrollBar.AsNeeded



            Column {

                width: parent.width - Theme.spacingLg * 2

                anchors.horizontalCenter: parent.horizontalCenter

                topPadding: Theme.spacingMd

                bottomPadding: Theme.spacingLg



                InsightTabRecommend {

                    width: parent.width

                    nextWatch: root.nextWatch

                    hiddenGems: root.hiddenGems

                    recs: root.recs

                }

            }

        }

    }



    Component {

        id: collectionTab

        AppScrollView {

            clip: true

            contentWidth: availableWidth

            ScrollBar.vertical.policy: ScrollBar.AsNeeded



            Column {

                width: parent.width - Theme.spacingLg * 2

                anchors.horizontalCenter: parent.horizontalCenter

                topPadding: Theme.spacingMd

                bottomPadding: Theme.spacingLg



                InsightTabCollection {

                    width: parent.width

                    libraryDist: root.libraryDist

                    actors: root.actors

                    genres: root.genres

                    makers: root.makers

                    actorCollections: root.actorCollections

                    pipeline: root.pipeline

                }

            }

        }

    }

}

