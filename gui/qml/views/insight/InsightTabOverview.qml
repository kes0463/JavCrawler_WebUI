import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"
import "../.."

ColumnLayout {
    id: tab
    width: parent ? parent.width : 0
    spacing: Theme.spacingLg

    property var weeklyDigest: ({})
    property var stats: ({})
    property var tasteData: ({})
    property var persona: ({})
    property var personaCoverageLabel: function() { return "" }
    property real viewportHeight: 0
    readonly property int profileCardHeight: 260

    property bool digestExpanded: false
    readonly property var digestLines: tab.weeklyDigest.lines || []
    readonly property bool digestHasData: !!(tab.weeklyDigest && tab.weeklyDigest.has_data)
    readonly property bool digestShowMore: tab.digestHasData && tab.digestLines.length > 3
    readonly property var digestVisibleLines: {
        if (!tab.digestShowMore || tab.digestExpanded)
            return tab.digestLines
        return tab.digestLines.slice(0, 3)
    }

    // ── 주간 리포트 ─────────────────────────────────────────────
    GlassCard {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        autoSize: false
        border.color: Qt.rgba(0, 229/255, 255/255, 0.35)
        Layout.preferredHeight: {
            if (!tab.digestHasData)
                return 72
            var n = tab.digestVisibleLines.length
            var h = 56 + n * 22
            if (tab.digestShowMore)
                h += 28
            return Math.max(72, h)
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            InsightSectionHeader {
                Layout.fillWidth: true
                icon: "📋"
                title: "지난 주 리포트"
                subtitle: tab.weeklyDigest.week_label || ""
            }

            Repeater {
                model: tab.digestHasData
                    ? tab.digestVisibleLines
                    : [tab.weeklyDigest.empty_message || "이번 주 시청 이력이 없습니다."]
                Text {
                    Layout.fillWidth: true
                    text: typeof modelData === "string" ? modelData : ""
                    font.pixelSize: Theme.fontCaption
                    color: tab.digestHasData ? Theme.textSecondary : Theme.textMuted
                    wrapMode: Text.Wrap
                }
            }

            Item {
                visible: tab.digestShowMore
                Layout.fillWidth: true
                Layout.preferredHeight: 24

                Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: tab.digestExpanded ? "접기" : "더 보기"
                    font.pixelSize: Theme.fontCaption
                    color: Theme.accentNeon
                    font.underline: true
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: tab.digestExpanded = !tab.digestExpanded
                }
            }
        }
    }

    InsightKpiGrid {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        stats: tab.stats
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: false
        Layout.preferredHeight: tab.profileCardHeight
        Layout.bottomMargin: Theme.spacingLg
        spacing: Theme.spacingMd

        TasteProfileCard {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            Layout.fillHeight: false
            Layout.preferredHeight: tab.profileCardHeight
            Layout.alignment: Qt.AlignTop
            profile: tab.tasteData
        }

        PersonaCard {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            Layout.fillHeight: false
            Layout.preferredHeight: tab.profileCardHeight
            Layout.alignment: Qt.AlignTop
            title: tab.persona.title || "나의 취향 페르소나"
            personaType: tab.persona.persona_type || ""
            summary: tab.persona.summary || tab.persona.body || ""
            body: tab.persona.body || tab.persona.summary || ""
            sensualSummary: tab.persona.sensual_summary || ""
            driftNote: tab.persona.drift_note || ""
            affinities: tab.persona.affinities || []
            turnOns: tab.persona.turn_ons || []
            avoidances: tab.persona.avoidances || []
            evidence: tab.persona.evidence || []
            semanticMatches: (tab.persona.semantic_profile && tab.persona.semantic_profile.nearest_unwatched)
                ? tab.persona.semantic_profile.nearest_unwatched
                : []
            generatedAt: tab.persona.generated_at || ""
            sourceLabel: tab.persona.source ? ("출처: " + tab.persona.source) : ""
            coverageLabel: tab.personaCoverageLabel(tab.persona)
            regenerating: InsightModel.isPersonaRegenerating
            onRegenerateRequested: InsightModel.regeneratePersona()
        }
    }

    Item { Layout.preferredHeight: Theme.spacingLg }
}
