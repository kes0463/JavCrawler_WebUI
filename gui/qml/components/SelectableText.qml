// SelectableText.qml – 선택·복사 가능한 읽기 전용 텍스트 컴포넌트
// Text와 동일하게 쓰되, 마우스로 드래그해 선택 / Ctrl+C 복사 가능
import QtQuick
import QtQuick.Controls

TextEdit {
    // ── 공개 프로퍼티 (Text 호환) ───────────────
    property alias text: root.text

    id: root
    /// 탭으로 모두 순회하지 않도록 — 클릭 후에만 포커스 (상세 화면 키보드 내비게이션용)
    focusPolicy: Qt.ClickFocus
    readOnly: true
    selectByMouse: true
    selectByKeyboard: true
    wrapMode: TextEdit.Wrap

    // 기본 스타일 (Theme에서 덮어 쓸 수 있음)
    color: "#b0b8cc"
    font.pixelSize: 14

    // 선택 색상
    selectionColor: Qt.rgba(0, 200/255, 255/255, 0.35)
    selectedTextColor: "#ffffff"

    // 커서를 텍스트 선택 가능 커서로
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.IBeamCursor
        acceptedButtons: Qt.NoButton   // 클릭 이벤트는 TextEdit에 위임
    }
}