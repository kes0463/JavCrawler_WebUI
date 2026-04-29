import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import QtQuick.Dialogs
import Qt5Compat.GraphicalEffects

Item {
    id: root

    /// 라이브러리 탭 전환 후 검색창에 포커스를 두어 키보드 체인이 항상 살아 있게 함 (main.qml Loader에서 호출)
    function forceLibraryFocus() {
        if (!detailVisible)
            Qt.callLater(function () {
                resetGridNavigation()
                libSearch.focusSearchInput()
            })
    }

    property bool detailVisible: false
    property bool selectMode: false
    property var selectedSkus: []

    function _isSelected(pc) {
        for (var i = 0; i < selectedSkus.length; i++) {
            if (selectedSkus[i] === pc)
                return true
        }
        return false
    }

    function _toggleSelected(pc, on) {
        var out = []
        var exists = false
        for (var i = 0; i < selectedSkus.length; i++) {
            var v = selectedSkus[i]
            if (v === pc) {
                exists = true
                if (on !== true)
                    continue
            }
            out.push(v)
        }
        if (!exists && on === true)
            out.push(pc)
        selectedSkus = out
    }

    onDetailVisibleChanged: {
        if (!detailVisible) {
            Qt.callLater(function () {
                resetGridNavigation()
                libSearch.focusSearchInput()
            })
        }
    }
    property string bindingProductCode: ""

    /// 검색창·필터·정렬 콤보 공통 높이
    readonly property int libToolbarH: 40

    /// 그리드 키보드 하이라이트 활성 여부
    property bool gridNavActive: false

    /// 휠 등 사용자 스크롤 후 다음 키 입력 시 뷰포트 첫 칸으로 맞출지 (프로그램 스크롤은 아래 플래그로 구분)
    property bool gridViewportSyncPending: false

    /// scrollIndexIntoView로 인한 contentY 변화는 휠 오인 방지용으로 무시
    property bool ignoreGridScrollDirty: false

    function gridCols() {
        return Math.max(1, Math.floor(grid.width / grid.cellWidth))
    }

    // 그리드 좌우에 남는 공간(첫 카드 모서리 기준선 보정용)
    function gridSideInset() {
        try {
            var cols = gridCols()
            var cw = grid.cellWidth
            var used = cols * cw
            return Math.max(0, (grid.width - used) / 2)
        } catch (e) {
            return 0
        }
    }

    function gridRowsVisible() {
        return Math.max(1, Math.floor(grid.height / grid.cellHeight))
    }

    function pageStepCount() {
        return gridCols() * gridRowsVisible()
    }

    function clampGridIndex(i) {
        if (grid.count <= 0)
            return 0
        return Math.max(0, Math.min(grid.count - 1, i))
    }

    /// 현재 스크롤 위치에서 화면 왼쪽 위에 보이는 칸의 인덱스 (휠 후 키보드 진입 시 기준)
    function firstVisibleGridIndex() {
        var cols = gridCols()
        if (grid.count <= 0 || cols <= 0)
            return 0
        var cw = grid.cellWidth
        var ch = grid.cellHeight
        if (cw <= 0 || ch <= 0)
            return 0
        var row = Math.floor(grid.contentY / ch)
        var col = Math.floor(grid.contentX / cw)
        row = Math.max(0, row)
        col = Math.max(0, Math.min(cols - 1, col))
        var idx = row * cols + col
        return clampGridIndex(idx)
    }

    function scrollIndexIntoView(i) {
        ignoreGridScrollDirty = true
        viewportScrollSuppressTimer.restart()
        grid.positionViewAtIndex(i, GridView.Contain)
    }

    function markViewportDirtyFromUserScroll() {
        if (ignoreGridScrollDirty)
            return
        if (!gridNavActive || !gridFocusScope.activeFocus)
            return
        gridViewportSyncPending = true
    }

    function applyGridArrow(event) {
        var cols = gridCols()
        var ci = grid.currentIndex
        var key = event.key
        if (key === Qt.Key_Left)
            ci -= 1
        else if (key === Qt.Key_Right)
            ci += 1
        else if (key === Qt.Key_Up)
            ci -= cols
        else if (key === Qt.Key_Down)
            ci += cols
        grid.currentIndex = clampGridIndex(ci)
        scrollIndexIntoView(grid.currentIndex)
    }

    function applyGridPage(deltaPages) {
        var step = pageStepCount()
        grid.currentIndex = clampGridIndex(grid.currentIndex + deltaPages * step)
        scrollIndexIntoView(grid.currentIndex)
    }

    /// 검색/툴바에서 그리드 키보드 내비로 진입 (정렬 콤보를 건너뜀 — 한 번에 포커스가 그리드로 가도록)
    function focusGridFromToolbar(preserveIndex) {
        if (grid.count <= 0)
            return
        gridNavActive = true
        if (!preserveIndex)
            grid.currentIndex = firstVisibleGridIndex()
        scrollIndexIntoView(grid.currentIndex)
        Qt.callLater(function () {
            gridFocusScope.forceActiveFocus()
            scrollIndexIntoView(grid.currentIndex)
        })
    }

    /// 첫 방향키: 0번에서 한 칸 이동 시도
    function activateGridNavigation(event) {
        gridNavActive = true
        grid.currentIndex = firstVisibleGridIndex()
        scrollIndexIntoView(grid.currentIndex)
        applyGridArrow(event)
        Qt.callLater(function () {
            gridFocusScope.forceActiveFocus()
            scrollIndexIntoView(grid.currentIndex)
        })
    }

    function resetGridNavigation() {
        gridNavActive = false
        gridViewportSyncPending = false
        ignoreGridScrollDirty = false
        viewportScrollSuppressTimer.stop()
    }

    Timer {
        id: viewportScrollSuppressTimer
        interval: 180
        repeat: false
        onTriggered: ignoreGridScrollDirty = false
    }

    Component.onCompleted: LibraryModel.reload()

    Connections {
        target: LibraryModel
        function onToastMessage(msg, level) { window.showToast(msg, level); }
        function onDetailLoaded() { root.detailVisible = true; }
        function onRequestFolderSelection(pc) {
            root.bindingProductCode = pc;
            manualFolderPicker.open();
        }
    }


    Shortcut {
        // StandardKey.Find(Ctrl+F)는 플랫폼마다 복수 시퀀스라 sequence: 대신 sequences: 필수
        sequences: ["/", StandardKey.Find]
        enabled: !root.detailVisible && !manualFolderPicker.visible
        onActivated: libSearch.focusSearchInput()
    }

    Shortcut {
        sequences: [StandardKey.Refresh]
        enabled: !root.detailVisible && !manualFolderPicker.visible
        onActivated: LibraryModel.reload()
    }

    // 라이브러리 진입 직후(검색창 포커스)에도 페이지/문서 이동키를 목록 스크롤로 처리
    Shortcut {
        sequences: ["PgUp"]
        enabled: !root.detailVisible && !manualFolderPicker.visible
        onActivated: {
            if (grid.count <= 0)
                return
            if (!gridNavActive) {
                gridNavActive = true
                grid.currentIndex = firstVisibleGridIndex()
            }
            Qt.callLater(function () { gridFocusScope.forceActiveFocus() })
            applyGridPage(-1)
        }
    }
    Shortcut {
        sequences: ["PgDown"]
        enabled: !root.detailVisible && !manualFolderPicker.visible
        onActivated: {
            if (grid.count <= 0)
                return
            if (!gridNavActive) {
                gridNavActive = true
                grid.currentIndex = firstVisibleGridIndex()
            }
            Qt.callLater(function () { gridFocusScope.forceActiveFocus() })
            applyGridPage(1)
        }
    }
    Shortcut {
        sequences: ["Home"]
        enabled: !root.detailVisible && !manualFolderPicker.visible
        onActivated: {
            if (grid.count <= 0)
                return
            gridNavActive = true
            grid.currentIndex = 0
            grid.positionViewAtBeginning()
            scrollIndexIntoView(0)
            Qt.callLater(function () { gridFocusScope.forceActiveFocus() })
        }
    }
    Shortcut {
        sequences: ["End"]
        enabled: !root.detailVisible && !manualFolderPicker.visible
        onActivated: {
            if (grid.count <= 0)
                return
            gridNavActive = true
            var last = grid.count - 1
            grid.currentIndex = last
            grid.positionViewAtEnd()
            scrollIndexIntoView(last)
            Qt.callLater(function () { gridFocusScope.forceActiveFocus() })
        }
    }

    /// 상세 화면에서 포커스가 스크롤/버튼 등에 있어도 목록으로 복귀 (루트 Keys는 포커스가 없으면 받지 못함)
    Shortcut {
        sequences: [StandardKey.Cancel]
        enabled: (root.detailVisible && detailLoader.item
            && !detailLoader.item.lightboxVisible
            && !detailLoader.item.folderPickerOpen
            && !manualFolderPicker.visible) || root.selectMode
        onActivated: {
            if (root.selectMode) {
                root.selectMode = false
                root.selectedSkus = []
            } else {
                root.detailVisible = false
            }
        }
    }

    Shortcut {
        sequences: ["Backspace"]
        enabled: root.detailVisible && detailLoader.item
            && !detailLoader.item.lightboxVisible
            && !detailLoader.item.folderPickerOpen
            && !manualFolderPicker.visible
        onActivated: root.detailVisible = false
    }

    FolderDialog {
        id: manualFolderPicker
        title: "작품(" + root.bindingProductCode + ") 폴더 선택"
        onAccepted: {
            var path = selectedFolder.toString();
            if (path.startsWith("file:///")) {
                path = path.replace("file:///","");
            }
            path = decodeURIComponent(path);
            LibraryModel.bindFolder(root.bindingProductCode, path);
        }
    }

    // ── 메인 목록 ───────────────────────────────────
    FocusScope {
        id: listPane
        anchors.fill: parent
        visible: !root.detailVisible
        focus: visible

        Keys.onPressed: function(event) {
            if (!visible || manualFolderPicker.visible)
                return
            var key = event.key
            var mods = event.modifiers
            // PgUp/PgDown/Home/End: 그리드 내비가 꺼져 있어도 목록 스크롤/이동으로 처리
            if (!(mods & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))
                    && (key === Qt.Key_PageUp || key === Qt.Key_PageDown || key === Qt.Key_Home || key === Qt.Key_End)
                    && !(libSearch.hasInputFocus || sortCombo.activeFocus || refreshBtn.activeFocus || libFilterBtn.activeFocus)
                    && grid.count > 0) {
                gridNavActive = true
                grid.currentIndex = firstVisibleGridIndex()
                scrollIndexIntoView(grid.currentIndex)
                Qt.callLater(function () { gridFocusScope.forceActiveFocus() })

                if (key === Qt.Key_PageUp) {
                    applyGridPage(-1)
                } else if (key === Qt.Key_PageDown) {
                    applyGridPage(1)
                } else if (key === Qt.Key_Home) {
                    grid.currentIndex = 0
                    grid.positionViewAtBeginning()
                    scrollIndexIntoView(0)
                } else if (key === Qt.Key_End) {
                    var last = grid.count - 1
                    grid.currentIndex = last
                    grid.positionViewAtEnd()
                    scrollIndexIntoView(last)
                }

                event.accepted = true
                return
            }
            var arrow = key === Qt.Key_Left || key === Qt.Key_Right || key === Qt.Key_Up || key === Qt.Key_Down
            if (!arrow || mods & Qt.ShiftModifier || mods & Qt.ControlModifier || mods & Qt.AltModifier)
                return
            if (libSearch.hasInputFocus || sortCombo.activeFocus || refreshBtn.activeFocus
                    || libFilterBtn.activeFocus)
                return
            if (gridNavActive)
                return
            // 목록 여백 등에서 방향키 → 그리드 첫 활성화 + 한 칸 이동
            if (grid.count > 0) {
                activateGridNavigation(event)
                event.accepted = true
            }
        }

        Column {
            id: contentColumn
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            RowLayout {
                width: parent.width

                Column {
                    spacing: 4
                    Text {
                        text: "라이브러리"
                        font.pixelSize: Theme.fontTitle
                        font.weight: Font.ExtraBold
                        color: Theme.textPrimary
                    }
                    Row {
                        spacing: 8
                        Text {
                            text: LibraryModel.workCount + "건"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                        }
                        BusyIndicator {
                            visible: LibraryModel.isLoading
                            width: 16; height: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                ActionButton {
                    id: refreshBtn
                    text: "새로고침"
                    primary: false
                    focusPolicy: Qt.StrongFocus
                    onClicked: LibraryModel.reload()
                    onFocusChanged: function() {
                        if (refreshBtn.focus)
                            resetGridNavigation()
                    }

                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            LibraryModel.reload()
                            event.accepted = true
                            return
                        }
                        if (event.key === Qt.Key_Down) {
                            libFilterBtn.forceActiveFocus()
                            event.accepted = true
                        }
                    }
                }
            }

            Row {
                id: toolbarRow
                spacing: Theme.spacingSm
                width: parent.width

                Button {
                    id: libFilterBtn
                    focusPolicy: Qt.StrongFocus
                    height: root.libToolbarH
                    width: root.libToolbarH
                    padding: 0
                    text: "\u2630"
                    flat: true
                    Accessible.role: Accessible.Button
                    Accessible.name: "라이브러리 필터"

                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: LibraryModel.filterMode !== 0 ? Theme.accentGlow : Theme.surfaceLight
                        border.color: libFilterBtn.activeFocus || LibraryModel.filterMode !== 0 ? Theme.accentNeon : Theme.glassBorder
                        border.width: 1
                        
                        // 필터 활성화 점(인디케이터)
                        Rectangle {
                            visible: LibraryModel.filterMode !== 0
                            width: 6; height: 6; radius: 3
                            color: Theme.accentNeon
                            anchors.top: parent.top
                            anchors.right: parent.right
                            anchors.margins: 4
                        }
                    }
                    contentItem: Text {
                        text: libFilterBtn.text
                        font.pixelSize: Theme.fontBody
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: LibraryModel.filterMode !== 0 ? Theme.accentNeon : Theme.textPrimary
                    }

                    onClicked: filterMenu.open()

                    Menu {
                        id: filterMenu
                        y: parent.height + 4
                        width: 160
                        padding: 6

                        background: Rectangle {
                            color: Theme.bgSecondary
                            border.color: Theme.glassBorderHover // 조금 더 밝은 경계선 사용
                            border.width: 1
                            radius: Theme.radiusSm
                            
                            // 그림자 효과 추가
                            layer.enabled: true
                            layer.effect: Component {
                                DropShadow {
                                    transparentBorder: true
                                    radius: 8
                                    samples: 17
                                    color: "#80000000"
                                }
                            }
                        }

                        // MenuItem 공통 스타일을 위한 컴포넌트화를 대신해 반복 수정
                        MenuItem {
                            id: mi0
                            text: "전체"
                            onTriggered: LibraryModel.filterMode = 0
                            font.pixelSize: 13
                            highlighted: LibraryModel.filterMode === 0
                            contentItem: Text {
                                text: mi0.text
                                font: mi0.font
                                color: mi0.highlighted ? Theme.accentNeon : Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 4
                            }
                        }
                        MenuItem {
                            id: mi1
                            text: "분석 완료"
                            onTriggered: LibraryModel.filterMode = 1
                            font.pixelSize: 13
                            highlighted: LibraryModel.filterMode === 1
                            contentItem: Text {
                                text: mi1.text
                                font: mi1.font
                                color: mi1.highlighted ? Theme.accentNeon : Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 4
                            }
                        }
                        MenuItem {
                            id: mi2
                            text: "분석 미완료"
                            onTriggered: LibraryModel.filterMode = 2
                            font.pixelSize: 13
                            highlighted: LibraryModel.filterMode === 2
                            contentItem: Text {
                                text: mi2.text
                                font: mi2.font
                                color: mi2.highlighted ? Theme.accentNeon : Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 4
                            }
                        }
                        MenuItem {
                            id: mi3
                            text: "폴더 연결됨"
                            onTriggered: LibraryModel.filterMode = 3
                            font.pixelSize: 13
                            highlighted: LibraryModel.filterMode === 3
                            contentItem: Text {
                                text: mi3.text
                                font: mi3.font
                                color: mi3.highlighted ? Theme.accentNeon : Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 4
                            }
                        }
                        MenuItem {
                            id: mi4
                            text: "자막 있음"
                            onTriggered: LibraryModel.filterMode = 4
                            font.pixelSize: 13
                            highlighted: LibraryModel.filterMode === 4
                            contentItem: Text {
                                text: mi4.text
                                font: mi4.font
                                color: mi4.highlighted ? Theme.accentNeon : Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 4
                            }
                        }
                    }

                    onFocusChanged: function() {
                        if (libFilterBtn.focus)
                            resetGridNavigation()
                    }

                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Right || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            libSearch.focusSearchInput()
                            event.accepted = true
                            return
                        }
                        if (event.key === Qt.Key_Down) {
                            libSearch.focusSearchInput()
                            event.accepted = true
                            return
                        }
                        if (event.key === Qt.Key_Up) {
                            refreshBtn.forceActiveFocus()
                            event.accepted = true
                        }
                    }
                }

                SearchBar {
                    id: libSearch
                    height: root.libToolbarH
                    placeholderText: "품번 · 제목 · 배우 · 장르 검색..."
                    width: 380
                    text: LibraryModel.searchQuery
                    onAccepted: function(q) { LibraryModel.searchQuery = q; }
                    onTextChanged: LibraryModel.searchQuery = text
                    onNavigateUp: refreshBtn.forceActiveFocus()
                    onNavigateDown: focusGridFromToolbar(false)
                    onNavigateLeft: libFilterBtn.forceActiveFocus()
                    onNavigateRight: {
                        sortCombo.forceActiveFocus()
                        Qt.callLater(function () { sortCombo.popup.open() })
                    }
                    onHasInputFocusChanged: {
                        if (libSearch.hasInputFocus)
                            resetGridNavigation()
                    }
                }

                ComboBox {
                    id: sortCombo
                    height: root.libToolbarH
                    width: 190
                    focusPolicy: Qt.StrongFocus
                    model: ["품번순", "날짜순 (최신)", "날짜순 (오래된)", "씬 수 (많은)", "최근 갱신순", "배우순 (ㄱ~ㅎ)", "배우순 (ㅎ~ㄱ)", "자막 있음 우선", "모파 우선"]
                    currentIndex: LibraryModel.sortMode
                    onCurrentIndexChanged: LibraryModel.sortMode = currentIndex

                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.surfaceLight
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                    contentItem: Text {
                        text: sortCombo.displayText
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textPrimary
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: Theme.spacingSm
                    }

                    onFocusChanged: function() {
                        if (sortCombo.focus)
                            resetGridNavigation()
                    }

                    Keys.onPressed: function(event) {
                        var mods = event.modifiers
                        // ← : 검색창으로 (드롭다운 열림이면 먼저 닫음)
                        if (event.key === Qt.Key_Left
                                && !(mods & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                            if (sortCombo.popup.open)
                                sortCombo.popup.close()
                            libSearch.focusSearchInput()
                            event.accepted = true
                            return
                        }
                        // 드롭다운 열림: 위/아래로 항목 이동·엔터 선택은 컨트롤 기본 동작
                        if (sortCombo.popup.open) {
                            event.accepted = false
                            return
                        }
                        // ↑ : 정렬 바로 위 열에 있는 새로고침으로 (검색 커서 조건 없이 도달 가능)
                        if (event.key === Qt.Key_Up
                                && !(mods & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                            refreshBtn.forceActiveFocus()
                            event.accepted = true
                            return
                        }
                        if (event.key === Qt.Key_Down) {
                            focusGridFromToolbar(false)
                            event.accepted = true
                        }
                    }
                }
            }

            // GridView는 Flickable — ScrollView로 한 번 더 감싸면 방향키/스크롤이 겹쳐 포커스·스크롤이 꼬임
            Item {
                width: parent.width
                height: parent.height - 130

                FocusScope {
                    id: gridFocusScope
                    anchors.fill: parent
                    focus: gridNavActive

                    Keys.onPressed: function(event) {
                        if (!gridNavActive || grid.count <= 0) {
                            event.accepted = false
                            return
                        }
                        var mods = event.modifiers

                        // 사용자 휠 스크롤 후: 첫 키 입력 전에 화면 왼쪽 위 칸으로 선택 맞춤 (프로그램 스크롤은 ignoreGridScrollDirty로 구분)
                        if (gridViewportSyncPending) {
                            grid.currentIndex = firstVisibleGridIndex()
                            scrollIndexIntoView(grid.currentIndex)
                            gridViewportSyncPending = false
                        }

                        // Alt+↑ → 검색창 (reset 전에 포커스 이동 — 안 그러면 gridNavActive 끊기며 포커스 유실)
                        if ((mods & Qt.AltModifier) && event.key === Qt.Key_Up) {
                            libSearch.focusSearchInput()
                            Qt.callLater(function () { resetGridNavigation() })
                            event.accepted = true
                            return
                        }
                        // Shift + 위/아래 페이지
                        if ((mods & Qt.ShiftModifier)
                                && (event.key === Qt.Key_Up || event.key === Qt.Key_Down)) {
                            applyGridPage(event.key === Qt.Key_Up ? -1 : 1)
                            event.accepted = true
                            return
                        }
                        // PgUp / PgDn
                        if (event.key === Qt.Key_PageUp) {
                            applyGridPage(-1)
                            event.accepted = true
                            return
                        }
                        // PgDn
                        if (event.key === Qt.Key_PageDown) {
                            applyGridPage(1)
                            event.accepted = true
                            return
                        }
                        // Home / End
                        if (event.key === Qt.Key_Home) {
                            grid.currentIndex = 0
                            grid.positionViewAtBeginning()
                            scrollIndexIntoView(0)
                            event.accepted = true
                            return
                        }
                        if (event.key === Qt.Key_End) {
                            var last = grid.count - 1
                            grid.currentIndex = last
                            grid.positionViewAtEnd()
                            scrollIndexIntoView(last)
                            event.accepted = true
                            return
                        }
                        // 맨 위 줄에서 ↑ → 검색창 (포커스 안착 후 reset — 한 번에 검색창으로 가도록)
                        if (event.key === Qt.Key_Up && grid.currentIndex < gridCols()) {
                            libSearch.focusSearchInput()
                            Qt.callLater(function () { resetGridNavigation() })
                            event.accepted = true
                            return
                        }
                        // Enter / Space → 상세
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                            var pc = grid.currentItem ? grid.currentItem.productCode : ""
                            if (pc !== "") {
                                if (root.selectMode) {
                                    root._toggleSelected(pc, !root._isSelected(pc))
                                } else {
                                    LibraryModel.loadDetail(pc)
                                }
                            }
                            event.accepted = true
                            return
                        }
                        // 방향키 이동
                        if (event.key === Qt.Key_Left || event.key === Qt.Key_Right
                                || event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                            if (!(mods & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier)))
                                applyGridArrow(event)
                            event.accepted = true
                            return
                        }
                    }

                    GridView {
                        id: grid
                        anchors.fill: parent
                        cellWidth: Math.floor(width / Math.max(1, Math.floor(width / 210)))
                        cellHeight: Math.floor(cellWidth * 1.48)
                        clip: true
                        // 이미지 그리드에서 cacheBuffer가 과하면 메모리/디코딩 부담이 커질 수 있음
                        cacheBuffer: 320
                        model: LibraryModel.works
                        boundsBehavior: Theme.boundsBehavior
                        flickDeceleration: Theme.flickDeceleration
                        maximumFlickVelocity: Theme.maxVelocity
                        interactive: true
                        keyNavigationEnabled: false
                        currentIndex: 0
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AlwaysOn
                            interactive: true
                        }
                        highlightMoveDuration: Theme.animNormal
                        highlightFollowsCurrentItem: true
                        highlight: Rectangle {
                            visible: gridNavActive && grid.count > 0
                            radius: Theme.radiusMd
                            border.color: Theme.accentNeon
                            border.width: 4
                            color: Theme.accentGlow
                        }

                        delegate: PosterCard {
                            width: grid.cellWidth
                            height: grid.cellHeight
                            productCode: model.productCode
                            titleKo: model.titleKo
                            actorsKo: model.actorsKo
                            sceneCount: model.sceneCount
                            coverPath: model.coverPath
                            previewPath: model.previewPath
                            pipelineStage: model.pipelineStage
                            hasCanonical: model.hasCanonical
                            partCount: model.partCount
                            hasJaSrt: model.hasJaSrt
                            hasKoSrt: model.hasKoSrt
                            lampHardcoded: model.lampHardcoded
                            lampMopa: model.lampMopa
                            selectionMode: root.selectMode
                            selected: root._isSelected(model.productCode)

                            onClicked: function(pc) {
                                if (root.selectMode) {
                                    root._toggleSelected(pc, !root._isSelected(pc))
                                } else {
                                    LibraryModel.loadDetail(pc)
                                }
                            }
                            
                            onPlayRequested: function(pc, rect) {
                                LibraryModel.loadDetail(pc)
                                Qt.callLater(function() {
                                    if (LibraryModel.detail.productCode === pc) {
                                        window.playVideo(pc, LibraryModel.detail.videoPath, LibraryModel.detail.titleKo, rect)
                                    }
                                })
                            }
                            
                            onSelectionToggled: function(sku, on) { root._toggleSelected(sku, on) }
                            onPressAndHold: function(sku) {
                                if (!root.selectMode) {
                                    root.selectMode = true
                                    root._toggleSelected(sku, true)
                                }
                            }
                        }
                    }

                    Connections {
                        target: grid
                        function onContentYChanged() {
                            markViewportDirtyFromUserScroll()
                            // 스크롤이 바닥 근처면 추가 로드(페이지네이션)
                            if (grid.contentY + grid.height >= grid.contentHeight - 800) {
                                if (LibraryModel.canLoadMore)
                                    LibraryModel.loadMore()
                            }
                        }
                        function onContentXChanged() {
                            markViewportDirtyFromUserScroll()
                        }
                    }
                }

                Text {
                    visible: grid.count === 0
                    anchors.centerIn: parent
                    text: "수집된 작품이 없습니다.\n「수집」 탭에서 크롤링하세요."
                    font.pixelSize: Theme.fontBody
                    color: Theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        // ── 선택 모드 하단 플로팅 액션바 ──────────────────
        Item {
            id: selectionPanelContainer
            anchors.bottom: parent.bottom
            // 카드 그리드의 실제 카드 시작/끝 기준선에 맞춘다.
            anchors.left: contentColumn.left
            anchors.right: contentColumn.right
            anchors.leftMargin: root.gridSideInset()
            anchors.rightMargin: root.gridSideInset()
            height: 72
            z: 1000
            
            visible: opacity > 0
            opacity: root.selectMode ? 1 : 0
            
            states: [
                State {
                    name: "visible"; when: root.selectMode
                    PropertyChanges { target: selectionPanelContainer; anchors.bottomMargin: 24; opacity: 1 }
                },
                State {
                    name: "hidden"; when: !root.selectMode
                    PropertyChanges { target: selectionPanelContainer; anchors.bottomMargin: -height; opacity: 0 }
                }
            ]
            
            transitions: Transition {
                NumberAnimation { properties: "anchors.bottomMargin, opacity"; duration: 400; easing.type: Easing.OutBack }
            }

            GlassCard {
                anchors.fill: parent
                radius: 36
                border.width: 2
                border.color: Theme.accentNeon
                
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 24
                    anchors.rightMargin: 12
                    spacing: 16

                    Column {
                        Layout.alignment: Qt.AlignVCenter
                        Text {
                            text: root.selectedSkus.length + "개 선택됨"
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.Bold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "다중 작업 수행 가능"
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textSecondary
                        }
                    }

                    Item { Layout.fillWidth: true }

                    ActionButton {
                        text: "몽타주 생성"
                        primary: true
                        neonGlow: true
                        enabled: root.selectedSkus.length >= 2
                        onClicked: {
                            MontageQueue.enqueue(root.selectedSkus)
                            root.selectMode = false
                            root.selectedSkus = []
                        }
                    }

                    ActionButton {
                        text: "모자이크 제거"
                        primary: true
                        neonGlow: true
                        enabled: root.selectedSkus.length >= 1
                        onClicked: {
                            LibraryModel.enqueueMosaicRemoval(root.selectedSkus)
                            root.selectMode = false
                            root.selectedSkus = []
                        }
                    }

                    ActionButton {
                        text: "재크롤링"
                        primary: false
                        neonGlow: true
                        enabled: root.selectedSkus.length >= 1
                        onClicked: {
                            HarvestModel.recrawlProducts(root.selectedSkus, true)
                            root.selectMode = false
                            root.selectedSkus = []
                        }
                    }

                    ActionButton {
                        text: "스토리 컨텍스트(Grok4.1)"
                        primary: false
                        neonGlow: true
                        enabled: root.selectedSkus.length >= 1
                        onClicked: {
                            LibraryModel.createStoryContextCacheForProducts(root.selectedSkus, false)
                            root.selectMode = false
                            root.selectedSkus = []
                        }
                    }

                    ActionButton {
                        text: "임베딩 생성"
                        primary: false
                        neonGlow: true
                        enabled: root.selectedSkus.length >= 1
                        onClicked: {
                            LibraryModel.createEmbeddingsForProducts(root.selectedSkus, false)
                            root.selectMode = false
                            root.selectedSkus = []
                        }
                    }

                    ActionButton {
                        text: "취소"
                        primary: false
                        onClicked: {
                            root.selectMode = false
                            root.selectedSkus = []
                        }
                    }
                }
            }
        }
    }

    // ── 상세 뷰 오버레이 ────────────────────────────
    Loader {
        id: detailLoader
        anchors.fill: parent
        active: root.detailVisible
        z: 2000
        sourceComponent: Component {
            LibraryDetail {
                onBack: root.detailVisible = false
            }
        }
    }
}