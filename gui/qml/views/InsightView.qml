import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import ".."

Item {
    id: root

    // ── 데이터 파싱 헬퍼 ────────────────────────────────────────────────────

    function parseJson(s, fallback) {
        try { var v = JSON.parse(s || ""); return v !== null ? v : fallback } catch(e) { return fallback }
    }

    function personaCoverageLabel(p) {
        if (!p || !p.coverage) return ""
        var c = p.coverage
        return "분석 샘플 — Grok " + (c.grok || 0) + " · 캐논 " + (c.canonical || 0) + " · 자막 " + (c.subtitle || 0)
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
    property var persona:     parseJson(InsightModel.personaCard,  {})
    property var pipeline:    parseJson(InsightModel.pipelineReport, {})
    property var stats:       parseJson(InsightModel.libraryStats, {})
    property var trend:       parseJson(InsightModel.recentTrend,  {actors:[], genres:[]})
    property var monthlyData: parseJson(InsightModel.monthlyGenres, [])
    property var tasteDrift:  parseJson(InsightModel.tasteDrift, {series:[]})
    property var libraryDist: parseJson(InsightModel.libraryDistribution, {actors:[], genres:[], makers:[]})
    property var weeklyDigest: parseJson(InsightModel.weeklyDigest, {lines:[]})

    // InsightModel 변경 시 로컬 프로퍼티 갱신
    Connections {
        target: InsightModel
        function onTopActorsChanged()    { root.actors      = root.parseJson(InsightModel.topActors, []) }
        function onTopGenresChanged()    { root.genres      = root.parseJson(InsightModel.topGenres, []) }
        function onTopMakersChanged()    { root.makers      = root.parseJson(InsightModel.topMakers, []) }
        function onTodayRecsChanged()    { root.recs        = root.parseJson(InsightModel.todayRecs, []) }
        function onNextWatchRecsChanged(){ root.nextWatch   = root.parseJson(InsightModel.nextWatchRecs, []) }
        function onHiddenGemsChanged()   { root.hiddenGems  = root.parseJson(InsightModel.hiddenGems, []) }
        function onActorCollectionsChanged() { root.actorCollections = root.parseJson(InsightModel.actorCollections, {actors:[]}) }
        function onTasteVectorChanged()  { root.tasteData   = root.parseJson(InsightModel.tasteVector, {axes:[]}) }
        function onWatchHeatmapChanged() { root.heatmapData = root.parseJson(InsightModel.watchHeatmap, {}) }
        function onPersonaCardChanged()  { root.persona     = root.parseJson(InsightModel.personaCard, {}) }
        function onPipelineReportChanged(){ root.pipeline   = root.parseJson(InsightModel.pipelineReport, {}) }
        function onLibraryStatsChanged() { root.stats       = root.parseJson(InsightModel.libraryStats, {}) }
        function onRecentTrendChanged()  { root.trend       = root.parseJson(InsightModel.recentTrend, {actors:[], genres:[]}) }
        function onMonthlyGenresChanged(){ root.monthlyData = root.parseJson(InsightModel.monthlyGenres, []) }
        function onTasteDriftChanged()    { root.tasteDrift  = root.parseJson(InsightModel.tasteDrift, {series:[]}) }
        function onLibraryDistributionChanged(){ root.libraryDist = root.parseJson(InsightModel.libraryDistribution, {actors:[], genres:[], makers:[]}) }
        function onWeeklyDigestChanged()     { root.weeklyDigest = root.parseJson(InsightModel.weeklyDigest, {lines:[]}) }
    }

    // ── 헤더 ────────────────────────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 상단 헤더바
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

                // 배치 동기화 버튼
                ActionButton {
                    text: InsightModel.isBatchRunning ? "동기화 중…" : "취향 재분석"
                    primary: true
                    enabled: !InsightModel.isBatchRunning
                    height: 38
                    onClicked: InsightModel.runBatch()
                }

                // 새로고침
                ActionButton {
                    text: "새로고침"
                    primary: false
                    height: 38
                    onClicked: InsightModel.refresh()
                }
            }

            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.glassBorder }
        }

        // 메인 스크롤 영역
        AppScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true

            ColumnLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.spacingLg
                spacing: Theme.spacingLg

                // ── 주간 취향 리포트 (다이제스트) ─────────────────
                GlassCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.weeklyDigest.has_data ? Math.max(100, 56 + (root.weeklyDigest.lines || []).length * 22) : 72
                    autoSize: false
                    border.color: Qt.rgba(0, 229/255, 255/255, 0.35)

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "📋 지난 주 리포트"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                visible: !!root.weeklyDigest.week_label
                                text: root.weeklyDigest.week_label || ""
                                font.pixelSize: Theme.fontCaption
                                color: Theme.accentNeon
                                leftPadding: Theme.spacingSm
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Repeater {
                            model: root.weeklyDigest.has_data ? (root.weeklyDigest.lines || []) : [root.weeklyDigest.empty_message || "이번 주 시청 이력이 없습니다."]

                            Text {
                                Layout.fillWidth: true
                                text: typeof modelData === "string" ? modelData : ""
                                font.pixelSize: Theme.fontCaption
                                color: root.weeklyDigest.has_data ? Theme.textSecondary : Theme.textMuted
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }

                // ── 통계 요약 카드 4종 ──────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMd

                    Repeater {
                        model: [
                            { label: "전체 작품", value: (root.stats.total || 0) + "편", icon: "📚" },
                            { label: "시청 완료", value: (root.stats.completed || 0) + "편", icon: "✅" },
                            { label: "완독률",    value: Math.round((root.stats.completion_rate || 0) * 100) + "%", icon: "📈" },
                            { label: "평균 별점", value: (root.stats.avg_rating || 0).toFixed(1) + "★", icon: "⭐" },
                            { label: "총 시청",   value: (root.stats.total_watch_hours || 0) + "시간", icon: "⏱" },
                        ]

                        GlassCard {
                            autoSize: false
                            Layout.fillWidth: true
                            Layout.preferredHeight: 90

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 4

                                Text {
                                    text: modelData.icon + " " + modelData.label
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.textSecondary
                                    Layout.alignment: Qt.AlignHCenter
                                }
                                Text {
                                    text: modelData.value
                                    font.pixelSize: Theme.fontSubtitle
                                    font.weight: Font.ExtraBold
                                    color: Theme.accentNeon
                                    Layout.alignment: Qt.AlignHCenter
                                }
                            }
                        }
                    }
                }

                // ── 취향 레이더 + 페르소나 ─────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.spacingLg
                    spacing: Theme.spacingMd

                    TasteProfileCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.alignment: Qt.AlignTop
                        profile: root.tasteData
                    }

                    PersonaCard {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        Layout.alignment: Qt.AlignTop
                        title: root.persona.title || "나의 취향 페르소나"
                        personaType: root.persona.persona_type || ""
                        summary: root.persona.summary || root.persona.body || ""
                        body: root.persona.body || root.persona.summary || ""
                        driftNote: root.persona.drift_note || ""
                        affinities: root.persona.affinities || []
                        evidence: root.persona.evidence || []
                        generatedAt: root.persona.generated_at || ""
                        sourceLabel: root.persona.source ? ("출처: " + root.persona.source) : ""
                        coverageLabel: root.personaCoverageLabel(root.persona)
                        regenerating: InsightModel.isPersonaRegenerating
                        onRegenerateRequested: InsightModel.regeneratePersona()
                    }
                }

                // ── 감상 캘린더 히트맵 ───────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 200
                    Layout.minimumHeight: 200
                    autoSize: false
                    clip: false
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacingMd
                            Text {
                                text: "📅 감상 캘린더"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: (root.heatmapData.year || new Date().getFullYear()) + "년"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                            }
                            Item { Layout.fillWidth: true }
                        }
                        AppScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 100
                            clip: true
                            contentWidth: heatmapInner.width
                            ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                            ScrollBar.vertical.policy: ScrollBar.AlwaysOff

                            HeatmapWidget {
                                id: heatmapInner
                                showYearLabel: false
                                year: root.heatmapData.year || new Date().getFullYear()
                                days: root.heatmapData.days || {}
                            }
                        }
                    }
                }

                // ── 취향 드리프트 (월별 장르 스택) ─────────────────
                GlassCard {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.spacingLg
                    Layout.preferredHeight: root.tasteDrift.has_data ? 260 : 120
                    Layout.minimumHeight: 120
                    autoSize: false
                    clip: false
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "📈 취향 드리프트"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: "최근 " + (root.tasteDrift.months_span || 6) + "개월 · 장르 비중"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                                leftPadding: Theme.spacingSm
                            }
                            Item { Layout.fillWidth: true }
                        }
                        AppScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: root.tasteDrift.has_data ? 200 : 48
                            clip: true
                            contentWidth: driftChartInner.implicitWidth
                            ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                            ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                            TasteDriftChart {
                                id: driftChartInner
                                timeline: root.tasteDrift
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Theme.spacingMd
                        }
                    }
                }

                // ── 파이프라인 운영 리포트 ─────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    autoSize: false
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingXs
                        Text {
                            text: "⚙️ 파이프라인 리포트 (최근 " + (root.pipeline.days || 30) + "일)"
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "이벤트 " + (root.pipeline.total_events || 0) + "건 · 오류 " + (root.pipeline.error_events || 0)
                                + "건 · 에러 JSON " + (root.pipeline.error_json_files || 0) + "개"
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textSecondary
                        }
                    }
                }

                // ── 보유 작품 통계 (Distribution) ──────────────────
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true
                    Layout.maximumWidth: 1200
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredHeight: 450

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingMd

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "📦 라이브러리 수집 현황"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: "보유 중인 전체 작품 수 기준"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                                leftPadding: Theme.spacingSm
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 40

                            // 배우별 보유 수
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                Layout.fillHeight: true
                                spacing: Theme.spacingMd
                                Text { text: "최다 보유 배우"; font.pixelSize: 15; color: Theme.textSecondary; font.weight: Font.DemiBold }
                                AppScrollView {
                                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                    contentWidth: availableWidth
                                    Column {
                                        width: parent.width; spacing: 2
                                        Repeater {
                                            model: root.libraryDist.actors || []
                                            Rectangle {
                                                width: parent.width
                                                height: distActorInner.implicitHeight + 8
                                                radius: 4
                                                color: distActorMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"

                                                RowLayout {
                                                    id: distActorInner
                                                    anchors { left: parent.left; right: parent.right; leftMargin: 4; rightMargin: 4; verticalCenter: parent.verticalCenter }
                                                    spacing: 8
                                                    Text {
                                                        text: modelData.name
                                                        font.pixelSize: 14
                                                        color: distActorMa.containsMouse ? Theme.accentNeon : Theme.textPrimary
                                                        Layout.fillWidth: true
                                                        elide: Text.ElideRight
                                                    }
                                                    Text {
                                                        text: modelData.count + "편"
                                                        font.pixelSize: 13
                                                        color: Theme.accentNeon
                                                        font.weight: Font.Bold
                                                        Layout.preferredWidth: 60
                                                        horizontalAlignment: Text.AlignRight
                                                    }
                                                }
                                                MouseArea {
                                                    id: distActorMa
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: window.navigateToLibrarySearch(modelData.name)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle { width: 1; Layout.fillHeight: true; color: Theme.glassBorder; Layout.topMargin: 20; Layout.bottomMargin: 20 }

                            // 장르별 보유 수
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                Layout.fillHeight: true
                                spacing: Theme.spacingMd
                                Text { text: "최다 보유 장르"; font.pixelSize: 15; color: Theme.textSecondary; font.weight: Font.DemiBold }
                                AppScrollView {
                                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                    contentWidth: availableWidth
                                    Column {
                                        width: parent.width; spacing: 2
                                        Repeater {
                                            model: root.libraryDist.genres || []
                                            Rectangle {
                                                width: parent.width
                                                height: distGenreInner.implicitHeight + 8
                                                radius: 4
                                                color: distGenreMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"

                                                RowLayout {
                                                    id: distGenreInner
                                                    anchors { left: parent.left; right: parent.right; leftMargin: 4; rightMargin: 4; verticalCenter: parent.verticalCenter }
                                                    spacing: 8
                                                    Text {
                                                        text: modelData.name
                                                        font.pixelSize: 14
                                                        color: distGenreMa.containsMouse ? "#FF9F43" : Theme.textPrimary
                                                        Layout.fillWidth: true
                                                        elide: Text.ElideRight
                                                    }
                                                    Text {
                                                        text: modelData.count + "편"
                                                        font.pixelSize: 13
                                                        color: "#FF9F43"
                                                        font.weight: Font.Bold
                                                        Layout.preferredWidth: 60
                                                        horizontalAlignment: Text.AlignRight
                                                    }
                                                }
                                                MouseArea {
                                                    id: distGenreMa
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: window.navigateToLibrarySearch(modelData.name)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle { width: 1; Layout.fillHeight: true; color: Theme.glassBorder; Layout.topMargin: 20; Layout.bottomMargin: 20 }

                            // 제작사별 보유 수
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                Layout.fillHeight: true
                                spacing: Theme.spacingMd
                                Text { text: "최다 보유 제작사"; font.pixelSize: 15; color: Theme.textSecondary; font.weight: Font.DemiBold }
                                AppScrollView {
                                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                    contentWidth: availableWidth
                                    Column {
                                        width: parent.width; spacing: 2
                                        Repeater {
                                            model: root.libraryDist.makers || []
                                            Rectangle {
                                                width: parent.width
                                                height: distMakerInner.implicitHeight + 8
                                                radius: 4
                                                color: distMakerMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"

                                                RowLayout {
                                                    id: distMakerInner
                                                    anchors { left: parent.left; right: parent.right; leftMargin: 4; rightMargin: 4; verticalCenter: parent.verticalCenter }
                                                    spacing: 8
                                                    Text {
                                                        text: modelData.name
                                                        font.pixelSize: 14
                                                        color: distMakerMa.containsMouse ? "#48DBFB" : Theme.textPrimary
                                                        Layout.fillWidth: true
                                                        elide: Text.ElideRight
                                                    }
                                                    Text {
                                                        text: modelData.count + "편"
                                                        font.pixelSize: 13
                                                        color: "#48DBFB"
                                                        font.weight: Font.Bold
                                                        Layout.preferredWidth: 60
                                                        horizontalAlignment: Text.AlignRight
                                                    }
                                                }
                                                MouseArea {
                                                    id: distMakerMa
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: window.navigateToLibrarySearch(modelData.name)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ── TOP 배우 & TOP 장르 나란히 ──────────────────
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMd

                    // TOP 5 배우
                    GlassCard {
                        autoSize: false
                        Layout.fillWidth: true
                        Layout.bottomMargin: Theme.spacingLg
                        Layout.preferredHeight: 340

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.spacingMd
                            spacing: Theme.spacingMd

                            Text {
                                text: "❤ 선호 배우 TOP 5"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                            Repeater {
                                model: root.actors.slice(0, 5)

                                Item {
                                    Layout.fillWidth: true
                                    implicitHeight: top5ActorRow.implicitHeight + 8

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 6
                                        color: top5ActorMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"
                                    }

                                    RowLayout {
                                        id: top5ActorRow
                                        anchors { left: parent.left; right: parent.right; leftMargin: 4; rightMargin: 4; verticalCenter: parent.verticalCenter }
                                        spacing: Theme.spacingSm

                                        // 순위 뱃지
                                        Rectangle {
                                            width: 28; height: 28; radius: 14
                                            color: index === 0 ? "#FFD700"
                                                 : index === 1 ? "#C0C0C0"
                                                 : index === 2 ? "#CD7F32"
                                                 : Theme.surfaceLight
                                            Text {
                                                anchors.centerIn: parent
                                                text: index + 1
                                                font.pixelSize: 12
                                                font.weight: Font.Bold
                                                color: index < 3 ? "#000" : Theme.textMuted
                                            }
                                        }

                                        Text {
                                            text: modelData.name || ""
                                            font.pixelSize: Theme.fontBody
                                            color: top5ActorMa.containsMouse ? Theme.accentNeon : Theme.textPrimary
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }

                                        // 점수 바
                                        Rectangle {
                                            property int maxScore: root.actors.length > 0
                                                ? (root.actors[0].score || 1) : 1
                                            property real ratio: Math.min(1.0,
                                                (modelData.score || 0) / maxScore)
                                            width: 100; height: 8; radius: 4
                                            color: Theme.progressTrack

                                            Rectangle {
                                                width: parent.ratio * parent.width
                                                height: parent.height; radius: 4
                                                color: Theme.accentNeon
                                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                                            }
                                        }

                                        Text {
                                            text: modelData.score || 0
                                            font.pixelSize: Theme.fontCaption
                                            color: Theme.textSecondary
                                            Layout.preferredWidth: 30
                                            horizontalAlignment: Text.AlignRight
                                        }
                                    }

                                    MouseArea {
                                        id: top5ActorMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: window.navigateToLibrarySearch(modelData.name)
                                    }
                                }
                            }

                            // 데이터 없을 때
                            Text {
                                visible: root.actors.length === 0
                                text: "아직 충분한 시청 데이터가 없습니다.\n영상을 시청하면 자동으로 분석됩니다."
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontCaption
                                horizontalAlignment: Text.AlignHCenter
                                Layout.alignment: Qt.AlignHCenter
                                wrapMode: Text.WordWrap
                            }

                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Theme.spacingMd
                            }
                        }
                    }

                    // TOP 장르
                    GlassCard {
                        autoSize: false
                        Layout.fillWidth: true
                        Layout.preferredHeight: 340

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.spacingMd
                            spacing: Theme.spacingMd

                            Text {
                                text: "🎬 선호 장르 TOP 8"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                            // 장르 리스트 스크롤 영역
                            AppScrollView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                contentWidth: availableWidth

                                Column {
                                    width: parent.width
                                    spacing: 2

                                    Repeater {
                                        model: root.genres.slice(0, 8)

                                        Rectangle {
                                            width: parent.width
                                            height: top8GenreInner.implicitHeight + 8
                                            radius: 6
                                            color: top8GenreMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"

                                            RowLayout {
                                                id: top8GenreInner
                                                anchors {
                                                    left: parent.left; right: parent.right
                                                    leftMargin: 4; rightMargin: 4
                                                    verticalCenter: parent.verticalCenter
                                                }
                                                spacing: Theme.spacingSm

                                                // 장르 색상 도트
                                                Rectangle {
                                                    width: 10; height: 10; radius: 5
                                                    color: _genreColor(index)
                                                    Layout.alignment: Qt.AlignVCenter
                                                }

                                                Text {
                                                    text: modelData.name || ""
                                                    font.pixelSize: Theme.fontCaption
                                                    color: top8GenreMa.containsMouse ? _genreColor(index) : Theme.textPrimary
                                                    Layout.fillWidth: true
                                                    elide: Text.ElideRight
                                                }

                                                Rectangle {
                                                    property int maxScore: root.genres.length > 0
                                                        ? (root.genres[0].score || 1) : 1
                                                    property real ratio: Math.min(1.0,
                                                        (modelData.score || 0) / maxScore)
                                                    Layout.preferredWidth: 80
                                                    height: 6; radius: 3
                                                    color: Theme.progressTrack
                                                    Layout.alignment: Qt.AlignVCenter

                                                    Rectangle {
                                                        width: parent.ratio * parent.width
                                                        height: parent.height; radius: 3
                                                        color: _genreColor(index)
                                                        Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                                                    }
                                                }

                                                Text {
                                                    text: modelData.score || 0
                                                    font.pixelSize: Theme.fontCaption
                                                    color: Theme.textSecondary
                                                    Layout.preferredWidth: 28
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                            }

                                            MouseArea {
                                                id: top8GenreMa
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: window.navigateToLibrarySearch(modelData.name)
                                            }
                                        }
                                    }

                                    Text {
                                        visible: root.genres.length === 0
                                        text: "장르 데이터 없음"
                                        color: Theme.textMuted
                                        font.pixelSize: Theme.fontCaption
                                        width: parent.width
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                }
                            }
                        }
                    }
                }

                // ── 최근 7일 취향 트렌드 ─────────────────────────
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true
                    Layout.preferredHeight: 200

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingMd

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "🔥 최근 7일 취향 트렌드"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: "최근 시청에 더 높은 가중치 적용"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                                Layout.alignment: Qt.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }

                        Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacingLg

                            // 최근 배우 트렌드
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text {
                                    text: "배우"
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.textSecondary
                                    font.weight: Font.DemiBold
                                }

                                Repeater {
                                    model: (root.trend.actors || []).slice(0, 3)
                                    Text {
                                        text: (index + 1) + ". " + (modelData.name || "")
                                            + "  (" + (modelData.recent_score || 0) + "점)"
                                        font.pixelSize: Theme.fontCaption
                                        color: index === 0 ? Theme.accentNeon : Theme.textPrimary
                                    }
                                }

                                Text {
                                    visible: (root.trend.actors || []).length === 0
                                    text: "데이터 없음"
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.textMuted
                                }
                            }

                            Rectangle { width: 1; Layout.fillHeight: true; color: Theme.glassBorder }

                            // 최근 장르 트렌드
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text {
                                    text: "장르"
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.textSecondary
                                    font.weight: Font.DemiBold
                                }

                                Repeater {
                                    model: (root.trend.genres || []).slice(0, 3)
                                    Text {
                                        text: (index + 1) + ". " + (modelData.name || "")
                                            + "  (" + (modelData.recent_score || 0) + "점)"
                                        font.pixelSize: Theme.fontCaption
                                        color: index === 0 ? "#FF9F43" : Theme.textPrimary
                                    }
                                }

                                Text {
                                    visible: (root.trend.genres || []).length === 0
                                    text: "데이터 없음"
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.textMuted
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }

                // ── 다음에 볼 작품 (스마트 추천) ─────────────────
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.nextWatch.length > 0 ? 380 : 120

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingMd

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "🎯 다음에 볼 작품"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: root.nextWatch.length > 0 && root.nextWatch[0].source === "embedding"
                                    ? "임베딩 기반 추천" : "취향 점수 기반 (규칙)"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                                leftPadding: Theme.spacingSm
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                        Row {
                            spacing: Theme.spacingMd
                            visible: root.nextWatch.length > 0

                            Repeater {
                                model: root.nextWatch.slice(0, 5)

                                Rectangle {
                                    id: recCard
                                    width: 150; height: 280
                                    radius: Theme.radiusMd
                                    color: Theme.surface
                                    border.color: recMa.containsMouse
                                        ? Theme.glassBorderHover : Theme.glassBorder
                                    border.width: 1
                                    clip: true

                                    scale: recMa.containsMouse ? 1.04 : 1.0
                                    Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }

                                    Column {
                                        anchors.fill: parent
                                        spacing: 0

                                        // 커버
                                        Rectangle {
                                            width: parent.width
                                            height: 200
                                            color: Theme.bgSecondary

                                            Image {
                                                anchors.fill: parent
                                                source: modelData.cover_path
                                                    ? "file:///" + modelData.cover_path : ""
                                                fillMode: Image.PreserveAspectCrop
                                                asynchronous: true
                                            }

                                            // 추천 점수 배지
                                            Rectangle {
                                                anchors.top: parent.top
                                                anchors.right: parent.right
                                                anchors.margins: 6
                                                width: 48; height: 22; radius: 11
                                                color: Qt.rgba(0, 229/255, 255/255, 0.9)

                                                Text {
                                                    anchors.centerIn: parent
                                                    text: Math.round((modelData.rec_score || 0) * 100) + "%"
                                                    font.pixelSize: 11
                                                    font.weight: Font.Bold
                                                    color: "#000"
                                                }
                                            }

                                            Text {
                                                anchors.centerIn: parent
                                                text: modelData.product_code || ""
                                                font.pixelSize: 14
                                                font.weight: Font.Bold
                                                color: Theme.textMuted
                                                visible: !modelData.cover_path
                                            }
                                        }

                                        // 정보
                                        Column {
                                            width: parent.width
                                            padding: 8
                                            spacing: 3

                                            Text {
                                                text: modelData.product_code || ""
                                                font.pixelSize: 11
                                                font.weight: Font.Bold
                                                color: Theme.accentNeon
                                                width: parent.width - 16
                                                elide: Text.ElideRight
                                            }
                                            Text {
                                                text: modelData.title_ko || "제목 없음"
                                                font.pixelSize: 11
                                                color: Theme.textPrimary
                                                width: parent.width - 16
                                                elide: Text.ElideRight
                                                maximumLineCount: 2
                                                wrapMode: Text.WordWrap
                                            }
                                            Text {
                                                text: modelData.actors_ko || ""
                                                font.pixelSize: 10
                                                color: Theme.textSecondary
                                                width: parent.width - 16
                                                elide: Text.ElideRight
                                                visible: !!modelData.actors_ko
                                            }
                                        }
                                    }

                                    MouseArea {
                                        id: recMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            window.navigateToLibraryDetail(modelData.product_code)
                                        }
                                    }
                                }
                            }
                        }

                        Text {
                            visible: root.nextWatch.length === 0
                            text: "아직 충분한 취향 데이터가 없습니다.\n영상을 시청하고 별점을 남기면 추천이 시작됩니다."
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontCaption
                            horizontalAlignment: Text.AlignHCenter
                            Layout.alignment: Qt.AlignHCenter
                            wrapMode: Text.WordWrap
                        }

                        Item { Layout.fillHeight: true }
                    }
                }

                // ── 숨은 보석 (Hidden Gems) ───────────────────────
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.spacingLg
                    Layout.preferredHeight: root.hiddenGems.length > 0 ? 380 : 120

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingMd

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "💎 놓친 보석"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: "미감상·저평가인데 취향과 잘 맞는 작품"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                                leftPadding: Theme.spacingSm
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                        Row {
                            spacing: Theme.spacingMd
                            visible: root.hiddenGems.length > 0

                            Repeater {
                                model: root.hiddenGems.slice(0, 6)

                                Rectangle {
                                    id: gemCard
                                    width: 150; height: 300
                                    radius: Theme.radiusMd
                                    color: Theme.surface
                                    border.color: gemMa.containsMouse
                                        ? Theme.glassBorderHover : Theme.glassBorder
                                    border.width: 1
                                    clip: true

                                    scale: gemMa.containsMouse ? 1.04 : 1.0
                                    Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }

                                    Column {
                                        anchors.fill: parent
                                        spacing: 0

                                        Rectangle {
                                            width: parent.width
                                            height: 200
                                            color: Theme.bgSecondary

                                            Image {
                                                anchors.fill: parent
                                                source: modelData.cover_path
                                                    ? "file:///" + modelData.cover_path : ""
                                                fillMode: Image.PreserveAspectCrop
                                                asynchronous: true
                                            }

                                            Rectangle {
                                                anchors.top: parent.top
                                                anchors.left: parent.left
                                                anchors.margins: 6
                                                height: 22
                                                radius: 11
                                                width: gemTypeLabel.implicitWidth + 12
                                                color: modelData.gem_type === "underrated"
                                                    ? Qt.rgba(1, 180/255, 80/255, 0.92)
                                                    : Qt.rgba(0.45, 0.75, 1, 0.92)

                                                Text {
                                                    id: gemTypeLabel
                                                    anchors.centerIn: parent
                                                    text: modelData.gem_type === "underrated" ? "재평가" : "미감상"
                                                    font.pixelSize: 10
                                                    font.weight: Font.Bold
                                                    color: "#000"
                                                }
                                            }

                                            Rectangle {
                                                anchors.top: parent.top
                                                anchors.right: parent.right
                                                anchors.margins: 6
                                                width: 48; height: 22; radius: 11
                                                color: Qt.rgba(0, 229/255, 255/255, 0.9)

                                                Text {
                                                    anchors.centerIn: parent
                                                    text: Math.round((modelData.rec_score || 0) * 100) + "%"
                                                    font.pixelSize: 11
                                                    font.weight: Font.Bold
                                                    color: "#000"
                                                }
                                            }

                                            Text {
                                                anchors.centerIn: parent
                                                text: modelData.product_code || ""
                                                font.pixelSize: 14
                                                font.weight: Font.Bold
                                                color: Theme.textMuted
                                                visible: !modelData.cover_path
                                            }
                                        }

                                        Column {
                                            width: parent.width
                                            padding: 8
                                            spacing: 3

                                            Text {
                                                text: modelData.product_code || ""
                                                font.pixelSize: 11
                                                font.weight: Font.Bold
                                                color: Theme.accentNeon
                                                width: parent.width - 16
                                                elide: Text.ElideRight
                                            }
                                            Text {
                                                text: modelData.title_ko || "제목 없음"
                                                font.pixelSize: 11
                                                color: Theme.textPrimary
                                                width: parent.width - 16
                                                elide: Text.ElideRight
                                                maximumLineCount: 2
                                                wrapMode: Text.WordWrap
                                            }
                                            Text {
                                                text: modelData.reason || ""
                                                font.pixelSize: 10
                                                color: Theme.textSecondary
                                                width: parent.width - 16
                                                wrapMode: Text.WordWrap
                                                maximumLineCount: 2
                                            }
                                        }
                                    }

                                    MouseArea {
                                        id: gemMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            window.navigateToLibraryDetail(modelData.product_code)
                                        }
                                    }
                                }
                            }
                        }

                        Text {
                            visible: root.hiddenGems.length === 0
                            text: "취향 데이터가 쌓이면 미감상·저평가 작품 중\n취향과 잘 맞는 보석을 찾아 드립니다."
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontCaption
                            horizontalAlignment: Text.AlignHCenter
                            Layout.alignment: Qt.AlignHCenter
                            wrapMode: Text.Wrap
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Theme.spacingMd
                        }
                    }
                }

                // ── 배우별 완독률 ─────────────────────────────────
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.actorCollections.has_data
                        ? Math.min(420, 80 + (root.actorCollections.actors || []).length * 28)
                        : 120

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "🎭 배우별 컬렉션 완성도"
                                font.pixelSize: Theme.fontBody
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: "보유 작품 대비 완독"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                                leftPadding: Theme.spacingSm
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }

                        AppScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.preferredHeight: root.actorCollections.has_data ? 280 : 48
                            clip: true
                            contentWidth: availableWidth
                            ActorCollectionCard {
                                width: parent.width
                                collection: root.actorCollections
                            }
                        }
                    }
                }

                // ── 오늘의 추천 (규칙) ───────────────────────────
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.recs.length > 0 ? 200 : 80
                    visible: root.recs.length > 0
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm
                        Text {
                            text: "✨ 오늘의 추천 (규칙)"
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: Theme.spacingSm
                            Repeater {
                                model: root.recs.slice(0, 6)
                                Rectangle {
                                    radius: Theme.radiusSm
                                    color: Theme.surfaceLight
                                    border.color: Theme.glassBorder
                                    height: 28
                                    width: recChipText.implicitWidth + 16
                                    Text {
                                        id: recChipText
                                        anchors.centerIn: parent
                                        text: (modelData.product_code || "") + " " + Math.round((modelData.rec_score || 0) * 100) + "%"
                                        font.pixelSize: Theme.fontCaption
                                        color: Theme.textPrimary
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: window.navigateToLibraryDetail(modelData.product_code)
                                    }
                                }
                            }
                        }
                    }
                }

                // ── 선호 제작사 ──────────────────────────────────
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true
                    Layout.preferredHeight: 180

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingMd

                        Text {
                            text: "🏢 선호 제작사 TOP 5"
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }

                        Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                        Flow {
                            Layout.fillWidth: true
                            spacing: Theme.spacingSm

                            Repeater {
                                model: root.makers.slice(0, 5)

                                Rectangle {
                                    radius: Theme.radiusSm
                                    color: Theme.surfaceLight
                                    border.color: Theme.glassBorder
                                    border.width: 1
                                    implicitWidth: makerChipRow.implicitWidth + Theme.spacingLg * 2
                                    implicitHeight: 36

                                    RowLayout {
                                        id: makerChipRow
                                        anchors.centerIn: parent
                                        anchors.leftMargin: Theme.spacingMd
                                        anchors.rightMargin: Theme.spacingMd
                                        spacing: Theme.spacingSm
                                        Text {
                                            id: makerLabel
                                            text: modelData.name || ""
                                            font.pixelSize: Theme.fontCaption
                                            color: Theme.textPrimary
                                        }
                                        Text {
                                            text: modelData.score || 0
                                            font.pixelSize: Theme.fontCaption
                                            color: Theme.accentNeon
                                            font.weight: Font.Bold
                                        }
                                    }
                                }
                            }

                            Text {
                                visible: root.makers.length === 0
                                text: "데이터 없음"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }

                Item { height: Theme.spacingLg }
            }
        }
    }

    // ── 색상 팔레트 헬퍼 ──────────────────────────────────────────────────────
    function _genreColor(idx) {
        var palette = [
            "#00E5FF", "#FF4081", "#FFD700", "#7C4DFF",
            "#00E676", "#FF9F43", "#48DBFB", "#FF6B6B",
        ]
        return palette[idx % palette.length]
    }
}