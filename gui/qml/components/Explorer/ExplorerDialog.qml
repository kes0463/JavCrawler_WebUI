import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../"
import "../"

Dialog {
    id: root
    width: 950
    height: 680
    modal: true
    anchors.centerIn: Overlay.overlay
    padding: 0
    
    // 외관 설정: 순정 탐색기는 Mica 효과가 주를 이룸
    background: GlassCard {
        anchors.fill: parent
        radius: 8
        border.width: 1
        border.color: Theme.glassBorder
        opacity: Theme.mode === 0 ? 0.95 : 1.0
    }

    contentItem: ColumnLayout {
        spacing: 0
        
        // ── 상단 툴바 (Command Bar) ─────────────────────
        ExplorerCommandBar {
            Layout.fillWidth: true
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }

        // ── 주소 및 탐색 컨트롤 ─────────────────────────
        ExplorerAddressBar {
            Layout.fillWidth: true
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }

        // ── 바디 (Sidebar + Content) ────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            ExplorerSidebar {
                Layout.fillHeight: true
                Layout.preferredWidth: 220
            }

            Rectangle { width: 1; Layout.fillHeight: true; color: Theme.glassBorder }

            FolderGrid {
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        // ── 푸터 (Actions) ─────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 64
            color: Theme.isDark ? "#1C1C1C" : "#F8F8F8"
            
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                
                Text {
                    text: FolderExplorerModel.selectionCount + "개 폴더 선택됨"
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontCaption + 1
                    visible: FolderExplorerModel.selectionCount > 0
                }

                Item { Layout.fillWidth: true }

                Row {
                    spacing: 12
                    
                    ActionButton {
                        text: "취소"
                        primary: false
                        onClicked: root.close()
                    }

                    ActionButton {
                        text: "선택 완료"
                        primary: true
                        enabled: FolderExplorerModel.selectionCount > 0 || FolderExplorerModel.currentPath !== ""
                        onClicked: {
                            FolderExplorerModel.confirmSelection();
                            root.accept();
                        }
                    }
                }
            }
        }
    }

    // 초기화 및 진입 경로 설정
    onOpened: {
        FolderExplorerModel.clearSelection();
    }
}