import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"
import "../.."

ColumnLayout {
    id: tab
    width: parent ? parent.width : 0
    spacing: Theme.spacingLg

    property var heatmapData: ({})
    property var tasteDrift: ({})
    property var trend: ({ actors: [], genres: [] })

    readonly property string trendSummary: {
        var a = (tab.trend.actors || [])[0]
        var g = (tab.trend.genres || [])[0]
        var parts = []
        if (a && a.name)
            parts.push("배우 " + a.name + " (" + (a.recent_score || 0) + "점)")
        if (g && g.name)
            parts.push("장르 " + g.name + " (" + (g.recent_score || 0) + "점)")
        return parts.length ? parts.join(" · ") : "최근 7일 시청 데이터 없음"
    }

    GlassCard {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        Layout.preferredHeight: 200
        Layout.minimumHeight: 200
        autoSize: false
        clip: false

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            InsightSectionHeader {
                Layout.fillWidth: true
                icon: "📅"
                title: "감상 캘린더"
                subtitle: (tab.heatmapData.year || new Date().getFullYear()) + "년"
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
                    year: tab.heatmapData.year || new Date().getFullYear()
                    days: tab.heatmapData.days || {}
                }
            }
        }
    }

    GlassCard {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        Layout.preferredHeight: tab.tasteDrift.has_data ? 300 : 140
        Layout.minimumHeight: 120
        autoSize: false
        clip: false

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            InsightSectionHeader {
                Layout.fillWidth: true
                icon: "📈"
                title: "취향 드리프트"
                subtitle: "최근 " + (tab.tasteDrift.months_span || 6) + "개월 · 장르 비중"
            }

            AppScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: tab.tasteDrift.has_data ? 200 : 48
                clip: true
                contentWidth: driftChartInner.implicitWidth
                ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                ScrollBar.vertical.policy: ScrollBar.AlwaysOff

                TasteDriftChart {
                    id: driftChartInner
                    timeline: tab.tasteDrift
                }
            }

            Text {
                Layout.fillWidth: true
                text: "🔥 최근 7일: " + tab.trendSummary
                font.pixelSize: Theme.fontCaption
                color: Theme.textMuted
                wrapMode: Text.Wrap
            }
        }
    }

    Item { Layout.preferredHeight: Theme.spacingLg }
}
