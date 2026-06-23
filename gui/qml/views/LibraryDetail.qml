import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtMultimedia
import ".."
import "../components"

/*
  LibraryDetail 키보드 매핑 (요약)

  포커스 순서:
  1. 방향키(아무거나) → cover 영역: 표지 패널 하이라이트
  2. ↓ 여러 번          → 본문 스크롤 → 미디어 폴더 카드 33% 이상 보이면 folder 포커스
  3. ← · →             → 폴더 연결 / 강제 연결 / 연결 해제 / 폴더 열기 순 이동
  4. ↓                  → snap 영역: 항상 0번(첫 번째) 스크린샷 포커스, 갤러리 상단 스크롤

  모드 browse(none):  방향키 → 커버 영역(cover) | Tab → 「목록으로」 포커스
  모드 cover:        ↑↓ 본문 스크롤 | 폴더 카드 33% 이상 보이면 ↓ → 폴더 연결 포커스 | Enter·Space 표지가 뷰에 충분히 보일 때만 라이트박스·아니면 폴더 행 | Tab 폴더 행
  모드 folder:       ←·→ 버튼 | ↑ 스크롤 위 | ↓ 스냅(있으면, idx=0으로 이동) | Enter·Space 실행
  모드 snap:         방향키 탐색 | 휠 후 첫 방향키 → 뷰포트 첫 썸네일 | 첫 줄 ↑ → 폴더 연결 | Enter 라이트박스 | Esc 폴더 행

  라이트박스:        Esc·Backspace → 닫기 | (←·→) 스틸 모드에서 이전·다음

  공통:              Esc·Backspace → 상세 닫기(root.back). LibraryView의 Shortcut(Cancel/Backspace)은
                     포커스 위치와 무관하게 목록으로 복귀할 수 있음(라이트박스·폴더 피커 열림 시 비활성).

  도움말:            F1(StandardKey.HelpContents) → 영역별 안내 패널
*/

Item {
    id: root
    signal back()

    function searchAndGoBack(q) {
        if (!q) return
        LibraryModel.searchQuery = q.trim()
        LibraryModel.clearDetailHistory()
        root.back()
    }

    function fileNameOnly(path) {
        if (!path)
            return ""
        var s = String(path)
        var a = s.lastIndexOf("/")
        var b = s.lastIndexOf("\\")
        var i = Math.max(a, b)
        return i >= 0 ? s.substring(i + 1) : s
    }


    /// 부모(LibraryView)에서 Shortcut 활성 조건용
    readonly property bool lightboxVisible: lightboxOverlay.visible

    property string folderBindMode: "normal"

    /// none | cover | folder | snap — 키보드 포커스 영역
    property string detailRegion: "none"
    property int folderBtnIdx: 0
    property int snapFocusIdx: 0

    property bool keyboardHelpVisible: false

    /** 표지 호버 다이제스트 미리보기 → 라이트박스 전체화면으로 이어 재생할 때(ms) */
    property int digestResumePositionMs: 0
    property int digestSeekPollCount: 0

    /** 표지 호버 하이라이트 미리보기 → 라이트박스 전체화면으로 이어 재생할 때(ms) */
    property int highlightResumePositionMs: 0
    property int highlightSeekPollCount: 0

    focus: true

    function resetDetailFocus() {
        detailRegion = "none"
        folderBtnIdx = 0
        snapFocusIdx = 0
        keyboardHelpVisible = false
    }

    function scrollMainByFraction(fr) {
        var f = mainScroll.contentItem
        if (!f || f.height <= 0)
            return
        // 스크롤 폭 제한 (화면 비율로 스크롤하되 최대 150px로 제한하여 한 번에 훅 점프하지 않도록 함)
        var distance = f.height * fr
        if (distance > 0) distance = Math.min(distance, 150)
        else distance = Math.max(distance, -150)

        var ny = f.contentY + distance
        ny = Math.max(0, Math.min(ny, Math.max(0, f.contentHeight - f.height)))
        f.contentY = ny
    }

    /// mapToItem(f, 0, 0) 은 뷰포트 Y를 반환 (0 = 뷰포트 상단).
    /// 뷰포트 Y 기준으로 카드의 50% 이상이 화면에 보이면 폴더 포커스 전환.
    function isFolderMediaCardInScrollView() {
        var f = mainScroll.contentItem
        if (!f || f.height <= 0 || folderMediaCard.height <= 0)
            return false
        var yTop = folderMediaCard.mapToItem(f, 0, 0).y   // 뷰포트 Y (스크롤 반영됨)
        var h = folderMediaCard.height
        var vh = f.height
        // 뷰포트 범위: [0, vh] — cy 와 섞으면 안 됨
        var visibleTop    = Math.max(yTop, 0)
        var visibleBottom = Math.min(yTop + h, vh)
        var visibleAmount = visibleBottom - visibleTop
        return visibleAmount >= h * 0.5
    }

    /// 스크롤로 표지 히어로가 거의 안 보이면 Enter는 표지 확대 대신 아래쪽(폴더 행)으로 간주
    function isCoverHeroSubstantiallyVisible() {
        var f = mainScroll.contentItem
        if (!f || f.height <= 0 || coverHeroCard.height <= 0)
            return false
        var yTop = coverHeroCard.mapToItem(f, 0, 0).y   // 뷰포트 Y
        var h = coverHeroCard.height
        var vh = f.height
        var overlap = Math.min(yTop + h, vh) - Math.max(yTop, 0)
        if (overlap <= 0)
            return false
        return overlap / h >= 0.22
    }

    function openCoverLightbox() {
        if (LibraryModel.detail.coverPath === "")
            return
        digestSeekApplyTimer.stop()
        digestSeekPollCount = 0
        highlightSeekApplyTimer.stop()
        highlightSeekPollCount = 0

        // 호버 중 하이라이트가 재생 중이면 현재 위치를 라이트박스 하이라이트로 이어 붙임
        digestResumePositionMs = 0
        if (coverHoverTimer.runningDigest && LibraryModel.detail.highlightPath !== "") {
            highlightResumePositionMs = highlightHoverPlayer.position
            highlightHoverPlayer.pause()
            lightboxOverlay.coverModePage = 1
        } else {
            highlightResumePositionMs = 0
            lightboxOverlay.coverModePage = 0
        }
        lightboxOverlay.coverMode = true
        lightboxOverlay.allViewMode = false
        lightboxImage.source = Theme.pathToUrl(LibraryModel.detail.coverPath)
        lightboxOverlay.visible = true
        zoomContainer.scale = 1.0
    }

    function closeLightboxOnly() {
        digestSeekApplyTimer.stop()
        digestResumePositionMs = 0
        digestSeekPollCount = 0
        highlightSeekApplyTimer.stop()
        highlightResumePositionMs = 0
        highlightSeekPollCount = 0
        zoomContainer.scale = 1.0
        zoomContainer.x = 0
        zoomContainer.y = 0
        // 풀스크린(라이트박스)에서 본 마지막 스틸 이미지를 QML 스냅 갤러리 인덱스에 연동
        if (lightboxOverlay.visible && !lightboxOverlay.coverMode && !lightboxOverlay.allViewMode) {
            if (LibraryModel.detail.stillPaths.length > 0) {
                root.snapFocusIdx = lightboxOverlay.currentIndex
                root.ensureSnapIndexVisible(root.snapFocusIdx)
            }
        }
        lightboxOverlay.visible = false
        lightboxOverlay.coverMode = false
        lightboxOverlay.allViewMode = false
        
        if (root.detailRegion === "snap") {
            root.focusSnapGallery()
        } else {
            root.forceActiveFocus()
        }
    }

    /// 스크롤/Flickable 직후 동기 forceActiveFocus는 무시되는 경우가 있어 다음 프레임에 맡김
    function focusFolderButton(btn) {
        if (!btn)
            return
        Qt.callLater(function () {
            btn.forceActiveFocus()
        })
    }

    /// 스냅 갤러리 스크롤 보정 — mapToItem 은 뷰포트 Y 반환, f.contentY 로 보정
    /// scrollToTop=true 이면 갤러리 상단으로 이동
    function ensureSnapGalleryVisible(scrollToTop) {
        var f = mainScroll.contentItem
        if (!f || f.height <= 0 || snapFocusScope.height <= 0)
            return
        var yTop = snapFocusScope.mapToItem(f, 0, 0).y   // 뷰포트 Y
        var yBot = yTop + snapFocusScope.height
        var vh = f.height
        var pad = 48
        if (scrollToTop) {
            // 갤러리 상단이 뷰포트 패드 위치에 오도록: contentY += yTop - pad
            f.contentY = Math.max(0, Math.min(f.contentY + yTop - pad, Math.max(0, f.contentHeight - vh)))
        } else if (yTop < pad) {
            f.contentY = Math.max(0, f.contentY + yTop - pad)
        } else if (yBot > vh - pad) {
            f.contentY = Math.min(Math.max(0, f.contentHeight - vh), f.contentY + yBot - (vh - pad))
        }
    }

    /// 폴더 카드가 뷰포트 안에 완전히 보이도록 스크롤 (버튼까지 노출)
    function scrollToRevealFolderCard() {
        var f = mainScroll.contentItem
        if (!f || f.height <= 0 || folderMediaCard.height <= 0)
            return
        var yTop = folderMediaCard.mapToItem(f, 0, 0).y   // 뷰포트 Y
        var yBot = yTop + folderMediaCard.height
        var vh = f.height
        var pad = 24
        if (yBot > vh - pad) {
            // 카드 하단이 잘려 있으면 아래로 스크롤하여 버튼 노출
            f.contentY = Math.min(Math.max(0, f.contentHeight - vh),
                                  f.contentY + yBot - (vh - pad))
        } else if (yTop < pad) {
            // 카드 상단이 위로 잘려 있으면 위로 스크롤
            f.contentY = Math.max(0, f.contentY + yTop - pad)
        }
    }

    /// 특정 인덱스의 스냅 썸네일이 뷰포트 안에 들어오게 스크롤
    function ensureSnapIndexVisible(idx) {
        var f = mainScroll.contentItem
        var cols = snapGrid.cols
        var ch = snapGrid.cellHeight
        if (!f || f.height <= 0 || cols <= 0 || ch <= 0) return
        var row = Math.floor(idx / cols)
        var cellYTop = snapGrid.mapToItem(f, 0, 0).y + row * ch
        var cellYBot = cellYTop + ch
        var vh = f.height
        var pad = 48
        if (cellYBot > vh - pad) {
            f.contentY = Math.min(Math.max(0, f.contentHeight - vh), f.contentY + cellYBot - (vh - pad))
        } else if (cellYTop < pad) {
            f.contentY = Math.max(0, f.contentY + cellYTop - pad)
        }
    }

    function focusSnapGallery(scrollToTop) {
        if (scrollToTop === true) {
            root.ensureSnapGalleryVisible(true)
        }
        folderBindBtn.focus = false
        folderForceBtn.focus = false
        folderClearBtn.focus = false
        folderOpenBtn.focus = false
        Qt.callLater(function () {
            snapFocusScope.forceActiveFocus()
            Qt.callLater(function () {
                if (!snapFocusScope.activeFocus)
                    snapFocusScope.forceActiveFocus()
            })
        })
    }

    /// 폴더 행 ActionButton 공통 키 처리 — slot: 0=연결 1=강제 2=해제 3=열기 — true면 처리함
    function handleFolderRowKey(event, slot) {
        /// 스냅 모드인데 포커스만 버튼에 남은 경우 → 격자 내비로 넘김 (아니면 첫 줄에서 detailRegion 이 folder 로 덮임)
        if (root.detailRegion === "snap")
            return root.processSnapNavigationKey(event.key, event.modifiers)
        root.detailRegion = "folder"
        root.folderBtnIdx = slot
        var k = event.key
        if (k === Qt.Key_Up) {
            root.scrollMainByFraction(-0.45)
            // 위로 스크롤한 결과, 표지 영역이 충분히 보이게 되거나 폴더 카드가 화면 아래로 밀려나면 표지 포커스로 복귀
            if (mainScroll.contentItem.contentY <= 10 || root.isCoverHeroSubstantiallyVisible() || !root.isFolderMediaCardInScrollView()) {
                root.detailRegion = "cover"
                folderBindBtn.focus = false
                folderForceBtn.focus = false
                folderClearBtn.focus = false
                folderOpenBtn.focus = false
                root.forceActiveFocus()
            }
            return true
        }
        if (k === Qt.Key_Right) {
            if (slot === 0) {
                root.focusFolderButton(folderForceBtn)
                root.folderBtnIdx = 1
            } else if (slot === 1) {
                root.focusFolderButton(folderClearBtn)
                root.folderBtnIdx = 2
            } else if (slot === 2) {
                root.focusFolderButton(folderOpenBtn)
                root.folderBtnIdx = 3
            }
            return true
        }
        if (k === Qt.Key_Left) {
            if (slot === 1) {
                root.focusFolderButton(folderBindBtn)
                root.folderBtnIdx = 0
            } else if (slot === 2) {
                root.focusFolderButton(folderForceBtn)
                root.folderBtnIdx = 1
            } else if (slot === 3) {
                root.focusFolderButton(folderClearBtn)
                root.folderBtnIdx = 2
            }
            return true
        }
        if (k === Qt.Key_Down) {
            if (LibraryModel.detail.stillPaths.length > 0) {
                root.detailRegion = "snap"
                // 폴더 행 ↓: 항상 첫 번째(0번) 스크린샷부터 포커스
                root.snapFocusIdx = 0
                root.focusSnapGallery(true)  // scrollToTop=true: 갤러리 상단으로 스크롤
            }
            return true
        }
        if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) {
            if (slot === 0) {
                root.folderBindMode = "normal"
                root.openFolderPicker()
            } else if (slot === 1) {
                root.folderBindMode = "force"
                root.openFolderPicker()
            } else if (slot === 2) {
                if (LibraryModel.detail.folderPath !== "")
                    LibraryModel.clearFolderBinding(LibraryModel.detail.productCode)
            } else if (slot === 3) {
                LibraryModel.openFolder(LibraryModel.detail.productCode)
            }
            return true
        }
        return false
    }

    /// 스냅 격자 방향키 — Shortcut/루트에서 포커스 없을 때도 동작
    function processSnapNavigationKey(key, mods) {
        root.detailRegion = "snap"
        var n = LibraryModel.detail.stillPaths.length
        if (n <= 0)
            return false
        if (root.snapFocusIdx >= n)
            root.snapFocusIdx = n - 1
        else if (root.snapFocusIdx < 0)
            root.snapFocusIdx = 0
        if (key === Qt.Key_Escape || key === Qt.Key_Back || key === Qt.Key_Backspace) {
            root.detailRegion = "folder"
            root.focusFolderButton(folderBindBtn)
            return true
        }

        var i = root.snapFocusIdx

        // 풀스크린(라이트박스) 진입 액션은 포커스 보정 타이머 이전에 먼저 가로채어 실행 (포커스 뺏기 충돌 방지)
        if (key === Qt.Key_Return || key === Qt.Key_Enter || key === Qt.Key_Space) {
            lightboxOverlay.coverMode = false
            lightboxOverlay.currentIndex = i
            lightboxImage.source = Theme.pathToUrl(LibraryModel.detail.stillPaths[i])
            lightboxOverlay.visible = true
            return true
        }

        /// 스코프에 활성 포커스가 없으면 보정 (Shortcut·루트만 타고 들어온 경우)
        if (!snapFocusScope.activeFocus)
            root.focusSnapGallery()

        var cols = snapGrid.cols
        if (key === Qt.Key_Up && i < cols) {
            root.detailRegion = "folder"
            root.focusFolderButton(folderBindBtn)
            return true
        }
        if (key === Qt.Key_Left)
            i = Math.max(0, i - 1)
        else if (key === Qt.Key_Right)
            i = Math.min(n - 1, i + 1)
        else if (key === Qt.Key_Up)
            i = Math.max(0, i - cols)
        else if (key === Qt.Key_Down) {
            if (i + cols < n)
                i += cols
        } else {
            return false
        }
        root.snapFocusIdx = i
        root.ensureSnapIndexVisible(i)
        return true
    }

    /// 폴더·스냅 자체 Keys가 없을 때만 창 단축키로 보조 (루트에 activeFocus 없으면 Keys가 안 먹음)
    /// 스냅: 격자(FocusScope)가 키를 받을 땐 창 단축키 끔 — activeFocus만으로는 불안정해 detailRegion도 함께 봄
    readonly property bool shortcutNavOk: !lightboxOverlay.visible && !folderPickerOpen && !keyboardHelpVisible
        && (detailRegion === "snap"
            || (!folderBindBtn.activeFocus && !folderForceBtn.activeFocus && !folderClearBtn.activeFocus && !folderOpenBtn.activeFocus))
        && !backToListBtn.activeFocus
        && !(detailRegion === "snap" && (snapFocusScope.activeFocus || snapGrid.activeFocus))

    /// none / cover 영역 키 내비 — true면 이벤트 소비됨
    function processDetailNavigationKey(key, mods) {
        var isArrow = key === Qt.Key_Left || key === Qt.Key_Right || key === Qt.Key_Up || key === Qt.Key_Down
        if (detailRegion === "none") {
            if (key === Qt.Key_Tab && !(mods & Qt.ShiftModifier)) {
                backToListBtn.forceActiveFocus()
                return true
            }
            if (isArrow && !(mods & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                detailRegion = "cover"
                return true
            }
            return false
        }
        if (detailRegion === "cover") {
            if (key === Qt.Key_Down && !(mods & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                if (root.isFolderMediaCardInScrollView()) {
                    detailRegion = "folder"
                    folderBtnIdx = 0
                    // 버튼까지 완전히 보이도록 스크롤 후 포커스
                    root.scrollToRevealFolderCard()
                    root.focusFolderButton(folderBindBtn)
                } else {
                    scrollMainByFraction(0.45)
                }
                return true
            }
            if (key === Qt.Key_Up && !(mods & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                scrollMainByFraction(-0.45)
                return true
            }
            if (key === Qt.Key_Return || key === Qt.Key_Enter || key === Qt.Key_Space) {
                if (LibraryModel.detail.coverPath !== "" && root.isCoverHeroSubstantiallyVisible()) {
                    openCoverLightbox()
                } else {
                    detailRegion = "folder"
                    folderBtnIdx = 0
                    root.focusFolderButton(folderBindBtn)
                }
                return true
            }
            if (key === Qt.Key_Tab && !(mods & Qt.ShiftModifier)) {
                detailRegion = "folder"
                folderBtnIdx = 0
                root.focusFolderButton(folderBindBtn)
                return true
            }
            return false
        }
        if (detailRegion === "folder") {
            return handleFolderRowKey({ key: key, modifiers: mods }, folderBtnIdx)
        }
        if (detailRegion === "snap") {
            return processSnapNavigationKey(key, mods)
        }
        return false
    }

    function keyboardHelpLines() {
        var L = []
        if (lightboxOverlay.visible) {
            L.push("Esc · Backspace — 뷰어 닫기")
            if (!lightboxOverlay.coverMode && !lightboxOverlay.allViewMode && LibraryModel.detail.stillPaths.length > 0)
                L.push("← · → — 스틸 이전 / 다음")
            return L
        }
        L.push("F1 — 도움말 패널")
        L.push("Esc · Backspace — 목록으로 돌아가기")
        switch (detailRegion) {
        case "none":
            L.push("방향키 — 커버 영역")
            L.push("Tab — 「목록으로」 버튼")
            break
        case "cover":
            L.push("↑ · ↓ — 본문 스크롤")
            L.push("미디어 폴더가 보일 때 ↓ — 폴더 연결 포커스")
            L.push("Enter · Space — 표지가 화면에 충분히 보일 때만 확대, 아니면 폴더 행")
            L.push("Tab — 폴더 버튼 행")
            break
        case "folder":
            L.push("← · → — 폴더 버튼 이동")
            L.push("↑ — 위로 스크롤")
            L.push("↓ — 스냅샷 격자(있을 때)")
            L.push("Enter · Space — 선택 동작")
            break
        case "snap":
            L.push("방향키 — 썸네일 (휠 후 첫 입력은 화면 첫 칸)")
            L.push("첫 줄에서 ↑ — 폴더 연결")
            L.push("Enter · Space — 확대")
            L.push("Esc · Backspace — 폴더 버튼으로")
            break
        }
        return L
    }

    Keys.onPressed: function(event) {
        if (lightboxOverlay.visible || root.folderPickerOpen || window.isPlayerOpen)
            return

        var key = event.key
        var mods = event.modifiers

        if (keyboardHelpVisible && (key === Qt.Key_Escape || key === Qt.Key_Back || key === Qt.Key_Backspace)) {
            keyboardHelpVisible = false
            event.accepted = true
            return
        }

        if (key === Qt.Key_Escape || key === Qt.Key_Back || key === Qt.Key_Backspace) {
            if (root.processDetailNavigationKey(key, mods)) {
                event.accepted = true
                return
            }
            
            // History navigation: if we can go back in history, do it
            if (LibraryModel.goBackDetail()) {
                event.accepted = true
                return
            }

            // Otherwise, exit to list
            LibraryModel.clearDetailHistory()
            root.back()
            event.accepted = true
            return
        }


        if (root.processDetailNavigationKey(key, mods)) {
            event.accepted = true
            return
        }
    }

    function urlToLocalPath(u) {
        var s = "" + u
        if (s.indexOf("file://") === 0) {
            s = s.replace("file://", "")
            if (s.length >= 3 && s[0] === "/" && s[2] === ":")
                s = s.slice(1)
        }
        try { s = decodeURIComponent(s) } catch (e) {}
        return s
    }

    /// 로컬 절대 경로 → FolderDialog.currentFolder용 file URL (Windows 드라이브 포함)
    function localPathToFolderUrl(localPath) {
        if (!localPath || localPath === "")
            return undefined
        var norm = ("" + localPath).replace(/\\/g, "/")
        if (norm.length >= 2 && norm.charAt(1) === ":" && norm.length === 2)
            norm = norm + "/"
        else
            norm = norm.replace(/\/+$/, "")
        if (norm.length < 2)
            return undefined
        // Windows: D:/foo → file:///D:/foo
        if (norm.charAt(1) === ":")
            return Theme.pathToUrl(norm)
        return Qt.url("file://" + norm)
    }

    function openFolderPicker() {
        var start = root.localPathToFolderUrl(LibraryModel.detail.folderPath)
        if (start !== undefined)
            folderPicker.currentFolder = start
        root.folderPickerOpen = true
        folderPicker.open()
    }

    property bool folderPickerOpen: false

    FolderDialog {
        id: folderPicker
        title: "작품(" + LibraryModel.detail.productCode + ") 폴더 연결"
        onAccepted: {
            root.folderPickerOpen = false
            var path = root.urlToLocalPath(selectedFolder.toString())
            if (root.folderBindMode === "force")
                LibraryModel.bindFolderForced(LibraryModel.detail.productCode, path, true)
            else
                LibraryModel.bindFolder(LibraryModel.detail.productCode, path)
        }
        onRejected: root.folderPickerOpen = false
    }

    Shortcut {
        sequences: [StandardKey.HelpContents]
        enabled: !root.folderPickerOpen
        onActivated: root.keyboardHelpVisible = !root.keyboardHelpVisible
    }

    Shortcut {
        sequences: ["Up"]
        enabled: root.shortcutNavOk && !root.activeFocus && !window.isPlayerOpen
        onActivated: root.processDetailNavigationKey(Qt.Key_Up, Qt.NoModifier)
    }
    Shortcut {
        sequences: ["Down"]
        enabled: root.shortcutNavOk && !root.activeFocus && !window.isPlayerOpen
        onActivated: root.processDetailNavigationKey(Qt.Key_Down, Qt.NoModifier)
    }
    Shortcut {
        sequences: ["Left"]
        enabled: root.shortcutNavOk && !root.activeFocus && !window.isPlayerOpen
        onActivated: root.processDetailNavigationKey(Qt.Key_Left, Qt.NoModifier)
    }
    Shortcut {
        sequences: ["Right"]
        enabled: root.shortcutNavOk && !root.activeFocus && !window.isPlayerOpen
        onActivated: root.processDetailNavigationKey(Qt.Key_Right, Qt.NoModifier)
    }
    Shortcut {
        sequences: ["Tab"]
        enabled: root.shortcutNavOk && !root.activeFocus && !window.isPlayerOpen
        onActivated: root.processDetailNavigationKey(Qt.Key_Tab, Qt.NoModifier)
    }
    Shortcut {
        sequences: ["Space"]
        enabled: root.shortcutNavOk && !root.activeFocus && !window.isPlayerOpen
        onActivated: root.processDetailNavigationKey(Qt.Key_Space, Qt.NoModifier)
    }
    Shortcut {
        sequences: ["Return", "Enter"]
        enabled: root.shortcutNavOk && !root.activeFocus && !window.isPlayerOpen
        onActivated: root.processDetailNavigationKey(Qt.Key_Return, Qt.NoModifier)
    }

    // ── 전체화면 이미지 뷰어 오버레이 ──────────────────
    Rectangle {
        id: lightboxOverlay
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.95)
        visible: false
        z: 100
        focus: visible

        property int currentIndex: 0
        property bool coverMode: false
        // 표지 전체화면(커버 모드) 3페이지: 0=표지, 1=하이라이트, 2=Digest
        // (없는 페이지는 좌/우 이동에서 자동 스킵)
        property int coverModePage: 0
        property bool allViewMode: false // 전체 보기 모드 여부
        property int allViewCols: 4 // 바둑판 너비(열 개수)

        // 상단 버튼(전체보기, 닫기) 포커스 네비게이션용 상태
        property bool topBtnFocus: false
        property int topBtnIndex: 0 // 0: 전체 보기, 1: 닫기

        Timer {
            id: lbFocusTimer
            interval: 0
            repeat: false
            onTriggered: lightboxOverlay.forceActiveFocus()
        }

        onVisibleChanged: {
            if (visible)
                lbFocusTimer.start()
        }

        Keys.onPressed: function (event) {
            if (event.key === Qt.Key_Escape || event.key === Qt.Key_Back || event.key === Qt.Key_Backspace) {
                // Backspace는 전체 보기에서 단일 보기로만 이동, 그밖의 ESC는 어디서든 라이트박스 완전 종료
                if (lightboxOverlay.allViewMode && (event.key === Qt.Key_Back || event.key === Qt.Key_Backspace)) {
                    lightboxOverlay.allViewMode = false
                    lightboxImage.source = "file:///" + LibraryModel.detail.stillPaths[lightboxOverlay.currentIndex]
                    event.accepted = true
                    return
                }
                root.closeLightboxOnly()
                event.accepted = true
                return
            }
            var k = event.key
            var paths = LibraryModel.detail.stillPaths
            var n = paths.length

            if (lightboxOverlay.coverMode) {
                function hasHighlight() { return LibraryModel.detail.highlightPath !== "" }
                function hasDigest() { return LibraryModel.detail.digestPath !== "" }

                function nextCoverPage() {
                    var p = lightboxOverlay.coverModePage
                    if (p === 0) {
                        if (hasHighlight()) return 1
                        if (hasDigest()) return 2
                        return 0
                    }
                    if (p === 1) {
                        if (hasDigest()) return 2
                        return 1
                    }
                    return 2
                }

                function prevCoverPage() {
                    var p2 = lightboxOverlay.coverModePage
                    if (p2 === 2) {
                        if (hasHighlight()) return 1
                        return 0
                    }
                    if (p2 === 1) return 0
                    return 0
                }

                if (k === Qt.Key_Left) {
                    var prev = prevCoverPage()
                    if (prev !== lightboxOverlay.coverModePage) {
                        lightboxOverlay.coverModePage = prev
                        zoomContainer.scale = 1.0
                    }
                    event.accepted = true
                } else if (k === Qt.Key_Right) {
                    var nxt = nextCoverPage()
                    if (nxt !== lightboxOverlay.coverModePage) {
                        lightboxOverlay.coverModePage = nxt
                        zoomContainer.scale = 1.0
                    }
                    event.accepted = true
                } else if (k === Qt.Key_Space) {
                    if (lightboxOverlay.coverModePage === 1) {
                        if (highlightFullscreenPlayer.playbackState === MediaPlayer.PlayingState) {
                            highlightFullscreenPlayer.pause()
                        } else {
                            highlightFullscreenPlayer.play()
                        }
                        event.accepted = true
                    } else if (lightboxOverlay.coverModePage === 2) {
                        if (digestFullscreenPlayer.playbackState === MediaPlayer.PlayingState) {
                            digestFullscreenPlayer.pause()
                        } else {
                            digestFullscreenPlayer.play()
                        }
                        event.accepted = true
                    }
                }
                return
            }

            // Tab 키로 개별 보기 ↔ 전체 보기 빠른 토글
            if (k === Qt.Key_Tab) {
                lightboxOverlay.allViewMode = !lightboxOverlay.allViewMode
                zoomContainer.scale = 1.0
                if (!lightboxOverlay.allViewMode)
                    lightboxImage.source = Theme.pathToUrl(paths[lightboxOverlay.currentIndex])
                event.accepted = true
                return
            }

            // 탑 버튼(전체보기, 닫기) 내비게이션
            if (lightboxOverlay.topBtnFocus) {
                if (k === Qt.Key_Down) {
                    lightboxOverlay.topBtnFocus = false  // 다시 화면 영역으로 복귀
                    event.accepted = true
                    return
                }
                if (k === Qt.Key_Left) {
                    if (!lightboxOverlay.coverMode) lightboxOverlay.topBtnIndex = 0
                    event.accepted = true
                    return
                }
                if (k === Qt.Key_Right) {
                    lightboxOverlay.topBtnIndex = 1
                    event.accepted = true
                    return
                }
                if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) {
                    if (lightboxOverlay.topBtnIndex === 0 && !lightboxOverlay.coverMode) {
                        lightboxOverlay.allViewMode = !lightboxOverlay.allViewMode
                        zoomContainer.scale = 1.0
                        if (!lightboxOverlay.allViewMode)
                            lightboxImage.source = Theme.pathToUrl(paths[lightboxOverlay.currentIndex])
                        lightboxOverlay.topBtnFocus = false
                    } else if (lightboxOverlay.topBtnIndex === 1) {
                        root.closeLightboxOnly()
                        lightboxOverlay.topBtnFocus = false
                    }
                    event.accepted = true
                    return
                }
                event.accepted = true
                return
            }

            // 전체 보기(바둑판) 모드에서의 키보드 네비게이션
            if (lightboxOverlay.allViewMode) {
                var cols = lightboxOverlay.allViewCols
                var i = lightboxOverlay.currentIndex
                if (k === Qt.Key_Left) i = Math.max(0, i - 1)
                else if (k === Qt.Key_Right) i = Math.min(n - 1, i + 1)
                else if (k === Qt.Key_Up) {
                    if (i < cols) {
                        // 맨 윗줄에서 위로 가면 상단 전체보기 버튼 포커스
                        lightboxOverlay.topBtnFocus = true
                        lightboxOverlay.topBtnIndex = 0
                        event.accepted = true
                        return
                    } else {
                        i -= cols
                    }
                }
                else if (k === Qt.Key_Down) {
                    if (i + cols < n) i += cols
                }
                else if (k === Qt.Key_Home) i = 0
                else if (k === Qt.Key_End) i = n - 1
                else if (k === Qt.Key_PageUp) i = Math.max(0, i - cols * 3)
                else if (k === Qt.Key_PageDown) i = Math.min(n - 1, i + cols * 3)
                else if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) {
                    lightboxOverlay.allViewMode = false
                    zoomContainer.scale = 1.0
                    lightboxImage.source = Theme.pathToUrl(paths[lightboxOverlay.currentIndex])
                    event.accepted = true
                    return
                }

                if (i !== lightboxOverlay.currentIndex) {
                    lightboxOverlay.currentIndex = i
                    allViewGrid.positionViewAtIndex(i, GridView.Contain)
                }
                event.accepted = true
                return
            }

            // 개별 보기 모드에서의 좌우 네비게이션
            if (k === Qt.Key_Up) {
                lightboxOverlay.topBtnFocus = true
                lightboxOverlay.topBtnIndex = (lightboxOverlay.coverMode ? 1 : 0)
                event.accepted = true
                return
            }
            if (k === Qt.Key_Left && lightboxOverlay.currentIndex > 0) {
                zoomContainer.scale = 1.0
                lightboxOverlay.currentIndex--
                lightboxImage.source = "file:///" + paths[lightboxOverlay.currentIndex]
                event.accepted = true
            } else if (k === Qt.Key_Right && lightboxOverlay.currentIndex < n - 1) {
                zoomContainer.scale = 1.0
                lightboxOverlay.currentIndex++
                lightboxImage.source = "file:///" + paths[lightboxOverlay.currentIndex]
                event.accepted = true
            }
        }

        // 배경 클릭으로 닫기 (줌 리셋 포함)
        MouseArea {
            anchors.fill: parent
            onClicked: {
                root.closeLightboxOnly()
            }
        }

        // 줌 및 드래그를 위한 플릭커블
        Flickable {
            boundsBehavior: Theme.boundsBehavior
            id: lightboxFlick
            anchors.fill: parent
            contentWidth: zoomContainer.width * zoomContainer.scale
            contentHeight: zoomContainer.height * zoomContainer.scale
            interactive: !lightboxOverlay.allViewMode
                && !(lightboxOverlay.coverMode && lightboxOverlay.coverModePage !== 0)
                && zoomContainer.scale > 1.0
            clip: true

            Item {
                id: zoomContainer
                width: lightboxFlick.width
                height: lightboxFlick.height
                scale: 1.0
                transformOrigin: Item.TopLeft

                Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

                onScaleChanged: {
                    if (scale <= 1.0) {
                        lightboxFlick.contentX = 0
                        lightboxFlick.contentY = 0
                    }
                }

                // 단일 이미지 보기 (썸네일 클릭 시 들어오는 원본 화면 또는 커버 화면)
                Image {
                    id: lightboxImage
                    anchors.centerIn: parent
                    width: parent.width * 0.95
                    height: parent.height * 0.95
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: (!lightboxOverlay.allViewMode) && !(lightboxOverlay.coverMode && (lightboxOverlay.coverModePage !== 0))
                    source: ""
                }

                // 하이라이트 극장 플레이어 (오디오 ON)
                MediaPlayer {
                    id: highlightFullscreenPlayer
                    source: LibraryModel.detail.highlightPath ? "file:///" + LibraryModel.detail.highlightPath : ""
                    videoOutput: highlightFullscreenVideo
                    loops: MediaPlayer.Infinite
                    audioOutput: highlightFullscreenAudio
                }

                AudioOutput {
                    id: highlightFullscreenAudio
                    volume: 1.0
                }

                VideoOutput {
                    id: highlightFullscreenVideo
                    anchors.centerIn: parent
                    width: parent.width * 0.95
                    height: parent.height * 0.95
                    fillMode: VideoOutput.PreserveAspectFit
                    visible: lightboxOverlay.coverMode && lightboxOverlay.coverModePage === 1

                    onVisibleChanged: {
                        if (visible) {
                            highlightFullscreenPlayer.pause()
                            var resumeH = root.highlightResumePositionMs
                            var dH = highlightFullscreenPlayer.duration
                            if (resumeH > 0 && dH > 0) {
                                root.highlightSeekPollCount = 0
                                highlightSeekApplyTimer.start()
                            } else {
                                highlightFullscreenPlayer.position = 0
                                highlightFullscreenPlayer.play()
                            }
                        } else {
                            highlightSeekApplyTimer.stop()
                            highlightFullscreenPlayer.pause()
                        }
                    }
                }

                Timer {
                    id: highlightSeekApplyTimer
                    interval: 50
                    repeat: true
                    onTriggered: {
                        root.highlightSeekPollCount += 1
                        var resume = root.highlightResumePositionMs
                        var d = highlightFullscreenPlayer.duration
                        if (resume > 0 && d > 0) {
                            highlightFullscreenPlayer.position = Math.min(
                                resume,
                                Math.max(0, d - 100))
                            root.highlightResumePositionMs = 0
                            highlightSeekApplyTimer.stop()
                            root.highlightSeekPollCount = 0
                            highlightFullscreenPlayer.play()
                        } else if (root.highlightSeekPollCount >= 40) {
                            highlightSeekApplyTimer.stop()
                            root.highlightSeekPollCount = 0
                            root.highlightResumePositionMs = 0
                            highlightFullscreenPlayer.play()
                        }
                    }
                }

                // 다이제스트 타임랩스 극장 플레이어 (무음 유지)
                MediaPlayer {
                    id: digestFullscreenPlayer
                    source: LibraryModel.detail.digestPath ? "file:///" + LibraryModel.detail.digestPath : ""
                    videoOutput: digestFullscreenVideo
                    loops: MediaPlayer.Infinite
                    audioOutput: null // 다이제스트 무당(묵음) 재생 보장
                }

                Timer {
                    id: digestSeekApplyTimer
                    interval: 50
                    repeat: true
                    onTriggered: {
                        root.digestSeekPollCount += 1
                        var resume = root.digestResumePositionMs
                        var d = digestFullscreenPlayer.duration
                        if (resume > 0 && d > 0) {
                            digestFullscreenPlayer.position = Math.min(
                                resume,
                                Math.max(0, d - 100))
                            root.digestResumePositionMs = 0
                            digestSeekApplyTimer.stop()
                            root.digestSeekPollCount = 0
                            digestFullscreenPlayer.play()
                        } else if (root.digestSeekPollCount >= 40) {
                            digestSeekApplyTimer.stop()
                            root.digestSeekPollCount = 0
                            root.digestResumePositionMs = 0
                            digestFullscreenPlayer.play()
                        }
                    }
                }

                VideoOutput {
                    id: digestFullscreenVideo
                    anchors.centerIn: parent
                    width: parent.width * 0.95
                    height: parent.height * 0.95
                    fillMode: VideoOutput.PreserveAspectFit
                    visible: lightboxOverlay.coverMode && lightboxOverlay.coverModePage === 2

                    onVisibleChanged: {
                        if (visible) {
                            digestFullscreenPlayer.pause()
                            var resume = root.digestResumePositionMs
                            if (resume > 0) {
                                root.digestSeekPollCount = 0
                                digestSeekApplyTimer.start()
                            } else {
                                digestFullscreenPlayer.position = 0
                                digestFullscreenPlayer.play()
                            }
                        } else {
                            digestSeekApplyTimer.stop()
                            digestFullscreenPlayer.pause()
                        }
                    }
                }



                // 전체 보기 (그리드) 모드 - GridView로 성능 최적화
                GridView {
                    boundsBehavior: Theme.boundsBehavior
                    id: allViewGrid
                    width: parent.width * 0.9
                    height: parent.height * 0.8
                    anchors.centerIn: parent
                    cellWidth: Math.floor(width / lightboxOverlay.allViewCols)
                    cellHeight: cellWidth * 9 / 16
                    visible: lightboxOverlay.allViewMode
                    model: LibraryModel.detail.stillPaths
                    clip: true
                    cacheBuffer: 1000

                    delegate: Item {
                        width: allViewGrid.cellWidth
                        height: allViewGrid.cellHeight

                        Item {
                            anchors.fill: parent
                            anchors.margins: 4
                            scale: thumbMouseArea.containsMouse ? 1.05 : 1.0
                            z: thumbMouseArea.containsMouse ? 10 : 1
                            Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

                            Image {
                                anchors.fill: parent
                                source: "file:///" + modelData
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                
                                Rectangle {
                                    anchors.fill: parent
                                    color: Qt.rgba(1,1,1,0.05)
                                    visible: parent.status === Image.Loading
                                }
                            }

                            // 포커스 하이라이트 표시
                            Rectangle {
                                anchors.fill: parent
                                radius: Theme.radiusSm
                                color: "transparent"
                                border.color: Theme.accentNeon
                                border.width: lightboxOverlay.currentIndex === index ? 4 : 0
                                visible: lightboxOverlay.currentIndex === index
                                z: 2
                            }

                            // 썸네일 직접 클릭 시 해당 이미지를 바로 개별 보기로 전환
                            MouseArea {
                                id: thumbMouseArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    lightboxOverlay.currentIndex = index
                                    lightboxOverlay.allViewMode = false
                                    zoomContainer.scale = 1.0
                                    lightboxImage.source = "file:///" + modelData
                                }
                            }
                        }
                    }
                }
            }

            // 휠 이벤트로 확대/축소 및 바둑판 배열 개수 조절
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.NoButton
                onWheel: (wheel) => {
                    var wheelDelta = wheel.angleDelta.y !== 0 ? wheel.angleDelta.y : wheel.pixelDelta.y
                    if (wheelDelta === 0) {
                        wheel.accepted = false
                        return
                    }

                    if (lightboxOverlay.allViewMode) {
                        // 전체 보기: 마우스 휠로 썸네일 크기(열 개수)를 조절한다.
                        if (wheelDelta > 0) {
                            lightboxOverlay.allViewCols = Math.max(2, lightboxOverlay.allViewCols - 1)
                        } else {
                            lightboxOverlay.allViewCols = Math.min(8, lightboxOverlay.allViewCols + 1)
                        }
                        // 확대/축소 직후엔 현재 포커싱된 이미지가 항상 보이도록 화면 당겨주기
                        allViewGrid.positionViewAtIndex(lightboxOverlay.currentIndex, GridView.Contain)
                        wheel.accepted = true
                    } else if (!lightboxOverlay.allViewMode) {
                        // 개별 사진 확대/축소
                        var zoomStep = 0.15
                        if (wheelDelta > 0) {
                            zoomContainer.scale = Math.min(zoomContainer.scale + zoomStep, 5.0)
                        } else {
                            zoomContainer.scale = Math.max(zoomContainer.scale - zoomStep, 1.0)
                        }
                        if (zoomContainer.scale <= 1.0) {
                            lightboxFlick.contentX = 0
                            lightboxFlick.contentY = 0
                        }
                        wheel.accepted = true
                    }
                }
            }
        }

        // ── 상영관 전용 하위 컨트롤 (Flickable 외부로 이동하여 이벤트 가로채기 방지) ──
        Item {
            id: highlightSeekbarContainer
            width: parent.width * 0.8
            height: 36 // 마우스로 잡기 편하게 큰 영역 확보
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 40
            anchors.horizontalCenter: parent.horizontalCenter
            visible: lightboxOverlay.coverMode && lightboxOverlay.coverModePage === 1
            z: 999 // 모든 상영관 레이어보다 위에 표시

            // 시각적인 얇은 바
            Rectangle {
                width: parent.width
                height: 6
                anchors.centerIn: parent
                color: Qt.rgba(1, 1, 1, 0.2)
                radius: 3

                Rectangle {
                    height: parent.height
                    width: highlightFullscreenPlayer.duration > 0 ? (parent.width * (highlightFullscreenPlayer.position / highlightFullscreenPlayer.duration)) : 0
                    color: Theme.accentNeon
                    radius: 3
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                preventStealing: true // 중요: Flickable에 이벤트를 뺏기지 않음

                function updatePosition(mouse) {
                    if (highlightFullscreenPlayer.duration > 0) {
                        var p = Math.max(0, Math.min(width, mouse.x))
                        highlightFullscreenPlayer.position = (p / width) * highlightFullscreenPlayer.duration
                    }
                }

                onPressed: (mouse) => updatePosition(mouse)
                onPositionChanged: (mouse) => {
                    if (pressed) updatePosition(mouse)
                }
            }
        }

        Item {
            id: digestSeekbarContainer
            width: parent.width * 0.8
            height: 36 // 마우스로 잡기 편하게 큰 영역 확보
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 40
            anchors.horizontalCenter: parent.horizontalCenter
            visible: lightboxOverlay.coverMode && lightboxOverlay.coverModePage === 2
            z: 999 // 모든 상영관 레이어보다 위에 표시

            // 시각적인 얇은 바
            Rectangle {
                width: parent.width
                height: 6
                anchors.centerIn: parent
                color: Qt.rgba(1, 1, 1, 0.2)
                radius: 3

                Rectangle {
                    height: parent.height
                    width: digestFullscreenPlayer.duration > 0 ? (parent.width * (digestFullscreenPlayer.position / digestFullscreenPlayer.duration)) : 0
                    color: Theme.accentNeon
                    radius: 3
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                preventStealing: true // 중요: Flickable에 이벤트를 뺏기지 않음

                function updatePosition(mouse) {
                    if (digestFullscreenPlayer.duration > 0) {
                        var p = Math.max(0, Math.min(width, mouse.x))
                        digestFullscreenPlayer.position = (p / width) * digestFullscreenPlayer.duration
                    }
                }

                onPressed: (mouse) => updatePosition(mouse)
                onPositionChanged: (mouse) => {
                    if (pressed) updatePosition(mouse)
                }
            }
        }

        // 닫기 버튼
        Rectangle {
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.margins: 24
            width: 44; height: 44
            radius: 22
            color: Qt.rgba(1,1,1,0.15)
            border.color: (lightboxOverlay.topBtnFocus && lightboxOverlay.topBtnIndex === 1) ? Theme.accentNeon : Qt.rgba(1,1,1,0.2)
            border.width: (lightboxOverlay.topBtnFocus && lightboxOverlay.topBtnIndex === 1) ? 3 : 1
            z: 110

            Text {
                anchors.centerIn: parent
                text: "✕"
                font.pixelSize: 20
                color: "#ffffff"
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    root.closeLightboxOnly()
                }
                cursorShape: Qt.PointingHandCursor
            }
        }

        // 전체 보기 토글 버튼
        Rectangle {
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: 24
            anchors.rightMargin: 84
            width: 110; height: 44
            radius: 22
            color: lightboxOverlay.allViewMode ? Theme.accentNeon : Qt.rgba(1,1,1,0.12)
            visible: !lightboxOverlay.coverMode
            z: 110
            
            border.color: (lightboxOverlay.topBtnFocus && lightboxOverlay.topBtnIndex === 0) ? Theme.accentNeon : "transparent"
            border.width: (lightboxOverlay.topBtnFocus && lightboxOverlay.topBtnIndex === 0) ? 3 : 0

            Text {
                anchors.centerIn: parent
                text: lightboxOverlay.allViewMode ? "개별 보기" : "전체 보기"
                font.pixelSize: 14
                font.weight: Font.DemiBold
                color: lightboxOverlay.allViewMode ? "#000000" : "#ffffff"
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    lightboxOverlay.allViewMode = !lightboxOverlay.allViewMode
                    zoomContainer.scale = 1.0
                }
                cursorShape: Qt.PointingHandCursor
            }
        }

        // 이전 / 다음 버튼 (이미 구현된 네비게이션 로직 유지하되 줌 리셋 추가, 및 커버모드 대응)
        Rectangle {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 20
            width: 50; height: 50
            radius: 25
            color: Qt.rgba(1,1,1,0.12)
            visible: (!lightboxOverlay.coverMode && !lightboxOverlay.allViewMode && lightboxOverlay.currentIndex > 0) || (lightboxOverlay.coverMode && lightboxOverlay.coverModePage > 0)
            z: 110

            Text { anchors.centerIn: parent; text: "‹"; font.pixelSize: 32; color: "#ffffff" }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (lightboxOverlay.coverMode) {
                        // 커버 3페이지 이전
                        if (lightboxOverlay.coverModePage === 2 && LibraryModel.detail.highlightPath !== "") {
                            lightboxOverlay.coverModePage = 1
                        } else {
                            lightboxOverlay.coverModePage = 0
                        }
                        zoomContainer.scale = 1.0
                        return
                    }
                    zoomContainer.scale = 1.0
                    lightboxOverlay.currentIndex--
                    lightboxImage.source = "file:///" + LibraryModel.detail.stillPaths[lightboxOverlay.currentIndex]
                }
            }
        }

        Rectangle {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.rightMargin: 20
            width: 50; height: 50
            radius: 25
            color: Qt.rgba(1,1,1,0.12)
            visible: (!lightboxOverlay.coverMode && !lightboxOverlay.allViewMode && lightboxOverlay.currentIndex < LibraryModel.detail.stillPaths.length - 1) || (lightboxOverlay.coverMode && (LibraryModel.detail.highlightPath !== "" || LibraryModel.detail.digestPath !== "") && lightboxOverlay.coverModePage < 2)
            z: 110

            Text { anchors.centerIn: parent; text: "›"; font.pixelSize: 32; color: "#ffffff" }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (lightboxOverlay.coverMode) {
                        // 커버 3페이지 다음 (없는 페이지는 스킵)
                        if (lightboxOverlay.coverModePage === 0) {
                            if (LibraryModel.detail.highlightPath !== "") {
                                lightboxOverlay.coverModePage = 1
                            } else if (LibraryModel.detail.digestPath !== "") {
                                lightboxOverlay.coverModePage = 2
                            }
                        } else if (lightboxOverlay.coverModePage === 1) {
                            if (LibraryModel.detail.digestPath !== "") {
                                lightboxOverlay.coverModePage = 2
                            }
                        }
                        zoomContainer.scale = 1.0
                        return
                    }
                    zoomContainer.scale = 1.0
                    lightboxOverlay.currentIndex++
                    lightboxImage.source = Theme.pathToUrl(LibraryModel.detail.stillPaths[lightboxOverlay.currentIndex])
                }
            }
        }

        Text {
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottomMargin: 32
            text: lightboxOverlay.allViewMode ? "마우스 휠로 전체 줌인/아웃" : ((lightboxOverlay.currentIndex + 1) + " / " + LibraryModel.detail.stillPaths.length)
            font.pixelSize: 14
            color: Qt.rgba(1,1,1,0.7)
            visible: !lightboxOverlay.coverMode
            z: 110
        }
    }

    // ── 비동기 이벤트 핸들링 ──────────────────────────
    Connections {
        target: LibraryModel
        
        function onDetailLoaded() {
            root.resetDetailFocus()
            Qt.callLater(function () {
                root.forceActiveFocus()
                scrollFocusFixTimer.start()
            })
            // 상세 정보 로드 시 영상은 있는데 스크린샷이 없으면 자동 추출 시작
            if (LibraryModel.detail.stillPaths.length === 0 && LibraryModel.detail.videoPath !== "") {
                LibraryModel.generateSnapshots(LibraryModel.detail.productCode, LibraryModel.detail.videoPath)
            }
        }

        function onSnapshotProgress(curr, total) {
            // 이제 Property Binding으로 처리되므로 추가 로직 불필요
        }

        function onSnapshotFinished(success, msg) {
            if (!success) {
                LibraryModel.toastMessage("스냅샷 추출 실패: " + msg, "error")
            }
        }

        function onSimilarBackTriggered() {
            // Automatically re-open the similar products popup when navigating back
            var pc = LibraryModel.detail.productCode
            if (pc) {
                similarPopup.queryProductCode = pc
                similarPopup.isLoading = true
                similarPopup.open()
                LibraryModel.findSimilarProducts(pc)
            }
        }
    }


    /// AppScrollView 내부 Flickable이 방향키로 스크롤 포커스를 가져가면 루트 Keys가 동작하지 않음
    Timer {
        id: scrollFocusFixTimer
        interval: 0
        repeat: false
        onTriggered: {
            var ci = mainScroll.contentItem
            if (ci) {
                if (ci.focusPolicy !== undefined)
                    ci.focusPolicy = Qt.NoFocus
                if (ci.focus !== undefined)
                    ci.focus = false
            }
            if (ci && ci.contentItem) {
                if (ci.contentItem.focusPolicy !== undefined)
                    ci.contentItem.focusPolicy = Qt.NoFocus
                if (ci.contentItem.focus !== undefined)
                    ci.contentItem.focus = false
            }
        }
    }

    Component.onCompleted: scrollFocusFixTimer.start()

    // ── 메인 스크롤 영역 ───────────────────────────────
    AppScrollView {
        id: mainScroll
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        contentWidth: availableWidth
        focusPolicy: Qt.NoFocus

        Column {
            width: parent.width
            spacing: Theme.spacingLg

            // ── 뒤로가기 ──────────────────────────────
            ActionButton {
                id: backToListBtn
                text: "\u2190 목록으로"
                primary: false
                focusPolicy: Qt.StrongFocus
                onClicked: {
                    LibraryModel.clearDetailHistory()
                    root.back()
                }


                Keys.onPressed: function (event) {
                    if (event.key === Qt.Key_Backtab
                        || (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier))) {
                        root.detailRegion = "none"
                        root.forceActiveFocus()
                        event.accepted = true
                    }
                }
            }

            Flickable {
                boundsBehavior: Theme.boundsBehavior
                id: actionFlickable
                width: parent.width
                height: actionRow.implicitHeight
                contentWidth: actionRow.implicitWidth
                contentHeight: actionRow.implicitHeight
                clip: true
                visible: LibraryModel.detail.productCode !== ""

                Row {
                    id: actionRow
                    spacing: Theme.spacingSm

                    property var highlightState: ({ "status": "none", "progress": 0, "message": "" })
                    property var previewState: ({ "status": "none", "progress": 0, "message": "" })

                    Timer {
                        id: highlightStateTimer
                        interval: 200
                        repeat: true
                        running: actionFlickable.visible && LibraryModel.detail.productCode !== "" && !LibraryModel.detailEditing
                        onTriggered: {
                        try {
                            actionRow.highlightState = HighlightQueue.productState(LibraryModel.detail.productCode)
                        } catch (e) {
                            actionRow.highlightState = ({ "status": "none", "progress": 0, "message": "" })
                        }
                        try {
                            actionRow.previewState = PreviewQueue.productState(LibraryModel.detail.productCode)
                        } catch (e2) {
                            actionRow.previewState = ({ "status": "none", "progress": 0, "message": "" })
                        }
                    }
                }

                ActionButton {
                    text: "편집"
                    primary: false
                    visible: !LibraryModel.detailEditing
                    onClicked: LibraryModel.beginDetailEdit()
                }

                ActionButton {
                    text: "🔄 재크롤링"
                    primary: false
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        var pc = (LibraryModel.detail.productCode || "").trim()
                        if (pc !== "")
                            HarvestModel.recrawlProducts([pc], true)
                    }
                }

                ActionButton {
                    text: "♡ 좋아요만"
                    primary: false
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        var pc = (LibraryModel.detail.productCode || "").trim()
                        if (pc !== "")
                            HarvestModel.recrawlFavoritesOnly([pc])
                    }
                }

                ActionButton {
                    text: LibraryModel.detail.watchLater ? "나중에 볼 해제" : "나중에 볼"
                    primary: LibraryModel.detail.watchLater
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        var pc = (LibraryModel.detail.productCode || "").trim()
                        if (pc !== "")
                            LibraryModel.toggleWatchLater(pc)
                    }
                }

                Popup {
                    id: deleteDialog
                    modal: true
                    dim: true
                    focus: true
                    closePolicy: Popup.CloseOnEscape
                    padding: Theme.spacingMd
                    parent: Overlay.overlay
                    anchors.centerIn: Overlay.overlay
                    width: Math.min(520, Overlay.overlay.width - 48)
                    z: 250

                    property bool deleteFiles: false

                    background: Rectangle {
                        radius: Theme.radiusMd
                        color: Theme.bgSecondary
                        border.color: Theme.glassBorder
                        border.width: 1
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.spacingSm

                        Text {
                            text: "라이브러리 삭제"
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "작품 " + LibraryModel.detail.productCode + " 을(를) 라이브러리에서 삭제할까요?"
                            wrapMode: Text.WordWrap
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontBody
                            Layout.fillWidth: true
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: Theme.glassBorder
                        }

                        CheckBox {
                            id: deleteFilesCheck
                            text: "파일도 함께 삭제 (주의: 되돌릴 수 없음)"
                            checked: false
                            onToggled: deleteDialog.deleteFiles = checked
                        }

                        Text {
                            text: deleteFilesCheck.checked
                                  ? "DB + 작품 폴더(미디어/산출물)까지 함께 삭제합니다."
                                  : "DB 메타데이터만 삭제합니다. (파일은 유지)"
                            wrapMode: Text.WordWrap
                            color: deleteFilesCheck.checked ? Theme.warning : Theme.textMuted
                            font.pixelSize: Theme.fontCaption
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacingSm
                            Item { Layout.fillWidth: true }
                            ActionButton {
                                text: "취소"
                                primary: false
                                onClicked: deleteDialog.close()
                            }
                            ActionButton {
                                text: deleteFilesCheck.checked ? "삭제(파일 포함)" : "삭제"
                                primary: true
                                neonGlow: true
                                onClicked: {
                                    var pc = LibraryModel.detail.productCode
                                    deleteDialog.close()
                                    if (pc !== "") {
                                        LibraryModel.deleteFromLibrary(pc, deleteDialog.deleteFiles)
                                        LibraryModel.clearDetailHistory()
                                        root.back()
                                    }

                                }
                            }
                        }
                    }
                }

                ActionButton {
                    text: "🗑 삭제"
                    primary: false
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        deleteDialog.deleteFiles = false
                        deleteFilesCheck.checked = false
                        deleteDialog.open()
                    }
                }

                ActionButton {
                    text: "🔄 메타 재동기화"
                    primary: false
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        var pc = LibraryModel.detail.productCode
                        if (pc === "") {
                            window.showToast("품번이 없습니다.", "warning")
                            return
                        }
                        LibraryModel.resyncMetadataKoForProduct(pc)
                    }
                }

                ActionButton {
                    text: "\u23F1 전사 시작"
                    primary: false
                    neonGlow: true
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        if (LibraryModel.detail.folderPath === "") {
                            window.showToast("동영상을 전사하려면 먼저 폴더를 연결해주세요.", "info")
                            root.openFolderPicker()
                            return
                        }
                        LibraryModel.startSTTForDetail(LibraryModel.detail.productCode, LibraryModel.detail.folderPath)
                    }
                }

                ActionButton {
                    text: "\u2710 자막 생성"
                    primary: false
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        if (LibraryModel.detail.folderPath === "") {
                            window.showToast("자막을 생성하려면 먼저 폴더를 연결해주세요.", "info")
                            root.openFolderPicker()
                            return
                        }
                        if (!LibraryModel.detail.hasJaSrt) {
                            window.showToast("먼저 전사(STT)를 완료해야 자막을 생성할 수 있습니다.", "warning")
                            return
                        }
                        LibraryModel.startSubtitleForDetail(LibraryModel.detail.productCode, LibraryModel.detail.folderPath)
                    }
                }

                ActionButton {
                    text: "스토리 컨텍스트(Grok)"
                    primary: false
                    neonGlow: true
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        var pc = (LibraryModel.detail.productCode || "").trim()
                        if (pc === "") {
                            window.showToast("품번이 없습니다.", "warning")
                            return
                        }
                        LibraryModel.createStoryContextCacheForProducts([pc], false)
                    }
                }

                ActionButton {
                    text: "임베딩 생성"
                    primary: false
                    neonGlow: true
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        var pc = (LibraryModel.detail.productCode || "").trim()
                        if (pc === "") {
                            window.showToast("품번이 없습니다.", "warning")
                            return
                        }
                        LibraryModel.createEmbeddingsForProducts([pc], false)
                    }
                }

                ActionButton {
                    text: "유사 작품 추천"
                    primary: false
                    neonGlow: true
                    visible: !LibraryModel.detailEditing
                    onClicked: {
                        var pc = (LibraryModel.detail.productCode || "").trim()
                        if (pc === "") {
                            window.showToast("품번이 없습니다.", "warning")
                            return
                        }
                        similarPopup.queryProductCode = pc
                        similarPopup.isLoading = true
                        similarPopup.open()
                        LibraryModel.findSimilarProducts(pc)
                    }
                }

                ActionButton {
                    text: {
                        var st = actionRow.highlightState.status || "none"
                        var p = actionRow.highlightState.progress || 0
                        if (st === "queued") return "⏳ 하이라이트 대기"
                        if (st === "running") return "⏳ 하이라이트 생성 " + p + "%"
                        if (LibraryModel.detail.highlightPath !== "") return "🎬 하이라이트 재생성"
                        return "🎬 하이라이트 생성"
                    }
                    primary: false
                    neonGlow: true
                    visible: !LibraryModel.detailEditing
                    enabled: true
                    clip: true

                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: {
                            var st = actionRow.highlightState.status || "none"
                            var p = actionRow.highlightState.progress || 0
                            if (st !== "running") return 0
                            return parent.width * (p / 100.0)
                        }
                        color: Qt.rgba(56/255, 189/255, 248/255, 0.35)
                        visible: (actionRow.highlightState.status === "running")
                        Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutQuad } }
                    }
                    onClicked: {
                        if (LibraryModel.detail.videoPath === "") {
                            window.showToast("하이라이트를 생성하려면 동영상이 필요합니다.", "warning")
                            return
                        }
                        LibraryModel.generateHighlight(LibraryModel.detail.productCode, LibraryModel.detail.videoPath)
                    }
                }

                ActionButton {
                    text: {
                        var st = actionRow.previewState.status || "none"
                        var p = actionRow.previewState.progress || 0
                        if (st === "queued") return "⏳ 프리뷰 대기"
                        if (st === "running") return "⏳ 프리뷰 재생성 " + p + "%"
                        return "🖼 프리뷰 재생성"
                    }
                    primary: false
                    neonGlow: true
                    visible: !LibraryModel.detailEditing
                    enabled: true
                    clip: true

                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: {
                            var st = actionRow.previewState.status || "none"
                            var p = actionRow.previewState.progress || 0
                            if (st !== "running") return 0
                            return parent.width * (p / 100.0)
                        }
                        color: Qt.rgba(56/255, 189/255, 248/255, 0.35)
                        visible: (actionRow.previewState.status === "running")
                        Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutQuad } }
                    }

                    onClicked: {
                        if (LibraryModel.detail.videoPath === "") {
                            window.showToast("프리뷰를 재생성하려면 동영상이 필요합니다.", "warning")
                            return
                        }
                        PreviewQueue.regenerate(LibraryModel.detail.productCode, LibraryModel.detail.videoPath)
                    }
                }

                ActionButton {
                    text: "저장"
                    primary: true
                    visible: LibraryModel.detailEditing
                    onClicked: LibraryModel.saveDetailEdit()
                }
                ActionButton {
                    text: "취소"
                    primary: false
                    visible: LibraryModel.detailEditing
                    onClicked: LibraryModel.cancelDetailEdit()
                }
                }
            }

            // ── 히어로: 커버(좌) + 메타정보(우) ──────────
            Rectangle {
                id: coverHeroCard
                width: parent.width
                height: Math.max(340, metaColumn.implicitHeight + Theme.spacingXl * 2)
                radius: Theme.radiusLg
                color: Theme.bgSecondary
                clip: true

                // 배경 블러 이미지
                Image {
                    anchors.fill: parent
                    source: LibraryModel.detail.coverPath ? "file:///" + LibraryModel.detail.coverPath : ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    opacity: 0.18
                }

                // 배경 오버레이
                Rectangle {
                    anchors.fill: parent
                    color: Qt.rgba(10/255, 14/255, 26/255, 0.72)
                }

                Row {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingXl
                    spacing: Theme.spacingXl

                    // 왼쪽: 커버 이미지 전체 (클릭하면 확대)
                    Rectangle {
                        id: coverPanel
                        width: 210
                        height: parent.height
                        radius: Theme.radiusMd
                        color: Qt.rgba(0,0,0,0.4)
                        clip: true
                        border.color: root.detailRegion === "cover"
                            ? Theme.accentNeon
                            : (coverHover.containsMouse
                                ? Qt.rgba(0, 200/255, 255/255, 0.55)
                                : Qt.rgba(255,255,255,0.07))
                        border.width: root.detailRegion === "cover"
                            ? 3
                            : (coverHover.containsMouse ? 2 : 1)

                        Behavior on border.color { ColorAnimation { duration: 120 } }

                        Image {
                            anchors.fill: parent
                            source: LibraryModel.detail.coverPath ? Theme.pathToUrl(LibraryModel.detail.coverPath) : ""
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }

                        // 하이라이트 플레이어 컴포넌트 (호버 3초 후)
                        MediaPlayer {
                            id: highlightHoverPlayer
                            source: LibraryModel.detail.highlightPath ? Theme.pathToUrl(LibraryModel.detail.highlightPath) : ""
                            videoOutput: coverHoverHighlightVideo
                            loops: MediaPlayer.Infinite
                            audioOutput: highlightHoverAudio
                        }

                        VideoOutput {
                            id: coverHoverHighlightVideo
                            anchors.fill: parent
                            fillMode: VideoOutput.PreserveAspectCrop // 커버 패널 규격에 맞춰 꽉 차게 크롭
                            opacity: coverHoverTimer.runningDigest ? 1.0 : 0.0
                            visible: opacity > 0
                            Behavior on opacity { NumberAnimation { duration: 300 } }
                        }

                        AudioOutput {
                            id: highlightHoverAudio
                            volume: 1.0
                        }

                        Timer {
                            id: coverHoverTimer
                            interval: 100
                            repeat: true
                            property bool runningDigest: false
                            property int hoverMs: 0
                            onTriggered: {
                                if (!runningDigest) {
                                    hoverMs += 100
                                    // 3초 대기 후 재생 시작
                                    if (hoverMs >= 3000 && LibraryModel.detail.highlightPath !== "") {
                                        runningDigest = true
                                        highlightHoverPlayer.play()
                                    }
                                }
                            }
                        }

                        // 커버 없을 때 플레이스홀더
                        Text {
                            anchors.centerIn: parent
                            text: "🎬"
                            font.pixelSize: 48
                            visible: LibraryModel.detail.coverPath === ""
                        }

                        // 호버 시 확대 아이콘 / 움짤 재생 인디케이터 오버레이
                        Rectangle {
                            anchors.fill: parent
                            radius: Theme.radiusMd
                            color: Qt.rgba(0, 0, 0, coverHover.containsMouse ? (coverHoverTimer.runningDigest ? 0.0 : 0.38) : 0)
                            visible: LibraryModel.detail.coverPath !== ""

                            Behavior on color { ColorAnimation { duration: 120 } }

                            Text {
                                anchors.centerIn: parent
                                text: coverHoverTimer.runningDigest ? "" : "🔍" // 움짤 뷰 중엔 아이콘 제거
                                font.pixelSize: 32
                                opacity: coverHover.containsMouse && !coverHoverTimer.runningDigest ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 120 } }
                            }
                        }

                        MouseArea {
                            id: coverHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: LibraryModel.detail.coverPath !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
                            enabled: LibraryModel.detail.coverPath !== ""

                            onEntered: {
                                coverHoverTimer.hoverMs = 0
                                coverHoverTimer.running = true
                            }
                            onExited: {
                                coverHoverTimer.running = false
                                coverHoverTimer.hoverMs = 0
                                coverHoverTimer.runningDigest = false
                                highlightHoverPlayer.pause()
                            }
                            onClicked: {
                                openCoverLightbox()
                            }
                        }
                    }

                    // 오른쪽: 메타 정보
                    Column {
                        id: metaColumn
                        width: parent.width - 210 - Theme.spacingXl
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.spacingSm

                        Column {
                            width: parent.width
                            spacing: Theme.spacingSm
                            visible: !LibraryModel.detailEditing

                            Row {
                                spacing: 16
                                Layout.fillWidth: true

                                SelectableText {
                                    text: LibraryModel.detail.productCode
                                    font.pixelSize: 42
                                    font.weight: Font.ExtraBold
                                    color: Theme.accentNeon
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                // [신규] 상단 재생 버튼
                                Rectangle {
                                    width: 44; height: 44; radius: 22
                                    color: detPlayMa.containsMouse ? Theme.accentNeon : "transparent"
                                    border.color: Theme.accentNeon
                                    border.width: 2
                                    visible: LibraryModel.detail.videoPath !== ""
                                    anchors.verticalCenter: parent.verticalCenter
                                    
                                    Text {
                                        anchors.centerIn: parent
                                        text: "▶"
                                        font.pixelSize: 20
                                        color: detPlayMa.containsMouse ? "#000" : Theme.accentNeon
                                        leftPadding: 3
                                    }
                                    
                                    MouseArea {
                                        id: detPlayMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            window.playVideo(
                                                LibraryModel.detail.productCode,
                                                LibraryModel.detail.videoPath,
                                                LibraryModel.detail.titleKo,
                                                Qt.rect(0, 0, 0, 0),
                                                LibraryModel.detail.videoPaths
                                            )
                                        }
                                    }
                                }
                            }

                            Column {
                                id: videoPartListCol
                                width: parent.width
                                spacing: 6
                                visible: LibraryModel.detail.videoPaths.length > 1

                                Text {
                                    text: "영상 파트"
                                    font.pixelSize: 11
                                    color: Theme.textSecondary
                                }

                                Repeater {
                                    model: LibraryModel.detail.videoPaths
                                    delegate: Rectangle {
                                        width: videoPartListCol.width
                                        height: 34
                                        radius: 6
                                        color: pathPartMa.containsMouse ? Theme.navHover : Theme.surfaceLight
                                        border.width: 1
                                        border.color: Theme.glassBorder

                                        property string partPath: (modelData !== undefined && modelData !== null)
                                            ? String(modelData)
                                            : ""

                                        Text {
                                            anchors.left: parent.left
                                            anchors.leftMargin: 10
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: (index + 1) + " — " + root.fileNameOnly(parent.partPath)
                                            font.pixelSize: 12
                                            color: Theme.textPrimary
                                            elide: Text.ElideRight
                                            width: parent.width - 52
                                        }
                                        Text {
                                            anchors.right: parent.right
                                            anchors.rightMargin: 10
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: "▶"
                                            font.pixelSize: 12
                                            color: Theme.accentNeon
                                        }
                                        MouseArea {
                                            id: pathPartMa
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                window.playVideo(
                                                    LibraryModel.detail.productCode,
                                                    parent.partPath,
                                                    LibraryModel.detail.titleKo,
                                                    Qt.rect(0, 0, 0, 0),
                                                    LibraryModel.detail.videoPaths
                                                )
                                            }
                                        }
                                    }
                                }
                            }

                            // 시청 통계 (횟수 / 누적 시간)
                            Row {
                                spacing: 14
                                visible: LibraryModel.detail.watchCount > 0

                                Text {
                                    text: "▶ " + LibraryModel.detail.watchCount + "회 시청"
                                    font.pixelSize: 12
                                    color: Theme.textSecondary
                                    verticalAlignment: Text.AlignVCenter
                                }

                                Text {
                                    visible: LibraryModel.detail.watchDuration > 0
                                    text: {
                                        var sec = LibraryModel.detail.watchDuration
                                        var h = Math.floor(sec / 3600)
                                        var m = Math.floor((sec % 3600) / 60)
                                        var s = sec % 60
                                        if (h > 0)
                                            return "⏱ " + h + "h " + m + "m 시청"
                                        else if (m > 0)
                                            return "⏱ " + m + "분 " + s + "초 시청"
                                        else
                                            return "⏱ " + s + "초 시청"
                                    }
                                    font.pixelSize: 12
                                    color: Theme.textSecondary
                                    verticalAlignment: Text.AlignVCenter
                                }

                                Text {
                                    visible: LibraryModel.detail.lastPosition > 5000
                                    text: {
                                        var ms = LibraryModel.detail.lastPosition
                                        var totalSec = Math.floor(ms / 1000)
                                        var h = Math.floor(totalSec / 3600)
                                        var m = Math.floor((totalSec % 3600) / 60)
                                        var s = totalSec % 60
                                        var pos = h > 0
                                            ? (h + ":" + String(m).padStart(2,"0") + ":" + String(s).padStart(2,"0"))
                                            : (m + ":" + String(s).padStart(2,"0"))
                                        return "⏩ " + pos + " 에서 재개"
                                    }
                                    font.pixelSize: 12
                                    color: Theme.accentNeon
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }

                            Row {
                                spacing: 10
                                Text {
                                    visible: LibraryModel.detail.favoriteScore > 0
                                    text: "♥ " + LibraryModel.detail.favoriteScore
                                    font.pixelSize: 13
                                    font.family: Theme.fontFamily
                                    color: "#FF4081"
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Text {
                                    visible: LibraryModel.detail.userLiked
                                    text: "내 \u2764"
                                    font.pixelSize: 12
                                    color: Theme.accentNeon
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Text {
                                    visible: LibraryModel.detail.userRating > 0
                                    text: "\u2605 " + LibraryModel.detail.userRating + "/5"
                                    font.pixelSize: 12
                                    color: Theme.warning
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Text {
                                    visible: LibraryModel.detail.hasFavoriteSiteDelta
                                    text: {
                                        var d = LibraryModel.detail.favoriteSiteDelta
                                        var days = LibraryModel.detail.favoriteSiteDeltaDays
                                        var pre = d > 0 ? ("+\u0394 " + d) : (d < 0 ? ("\u0394 " + d) : "\u0394 0")
                                        return pre + " (" + days + "\uC77C)"
                                    }
                                    font.pixelSize: 12
                                    font.family: Theme.fontFamily
                                    color: LibraryModel.detail.favoriteSiteDelta > 0 ? Theme.accentNeon
                                        : LibraryModel.detail.favoriteSiteDelta < 0 ? "#FF7043"
                                        : Theme.textMuted
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }

                            SelectableText {
                                text: LibraryModel.detail.titleKo || LibraryModel.detail.titleJa || "제목 없음"
                                font.pixelSize: Theme.fontTitle
                                font.weight: Font.Bold
                                color: Theme.textPrimary
                                width: parent.width
                                wrapMode: TextEdit.Wrap
                            }

                            Item { height: 4 }

                            RowLayout {
                                width: parent.width
                                spacing: 12
                                visible: LibraryModel.detail.actorsKo !== ""

                                Rectangle {
                                    Layout.preferredWidth: 3
                                    Layout.preferredHeight: actorFlow.height > 0 ? actorFlow.height : 18
                                    Layout.alignment: Qt.AlignTop
                                    color: Theme.accentNeon
                                    radius: 2
                                }

                                Flow {
                                    id: actorFlow
                                    Layout.fillWidth: true
                                    spacing: 6
                                    flow: Flow.LeftToRight
                                    layoutDirection: Qt.LeftToRight

                                    Repeater {
                                        id: actorRep
                                        model: {
                                            var s = LibraryModel.detail.actorsKo || ""
                                            var parts = s.split(",")
                                            var out = []
                                            for (var i = 0; i < parts.length; i++) {
                                                var t = parts[i].trim()
                                                if (t.length > 0)
                                                    out.push(t)
                                            }
                                            return out
                                        }

                                        delegate: Text {
                                            id: actorText
                                            text: modelData + (index < actorRep.count - 1 ? ", " : "")
                                            font.pixelSize: Theme.fontBody
                                            color: actorMa.containsMouse ? Theme.accentNeon : Theme.textSecondary
                                            font.underline: actorMa.containsMouse

                                            MouseArea {
                                                id: actorMa
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: window.navigateToActressByName(modelData)
                                            }
                                        }
                                    }
                                }
                            }

                            Row {
                                spacing: Theme.spacingMd
                                SelectableText {
                                    id: makerText
                                    text: LibraryModel.detail.makerKo || ""
                                    font.pixelSize: Theme.fontBody
                                    color: makerMa.containsMouse ? Theme.accentNeon : Theme.textMuted
                                    visible: text !== ""
                                    font.underline: makerMa.containsMouse

                                    MouseArea {
                                        id: makerMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.searchAndGoBack(LibraryModel.detail.makerKo)
                                        // SelectableText가 클릭을 가로채지 않도록 acceptedButtons: Qt.NoButton을 사용했었으나, 
                                        // 여기서는 검색 트리거가 우선이므로 기본 동작을 가로채도 됨.
                                    }
                                }
                                SelectableText {
                                    text: LibraryModel.detail.releaseDate ? ("📅 " + LibraryModel.detail.releaseDate) : ""
                                    font.pixelSize: Theme.fontBody
                                    color: Theme.textMuted
                                    visible: text !== ""
                                }
                            }

                            Flow {
                                width: parent.width
                                spacing: 6
                                visible: LibraryModel.detail.genresKo !== "" || LibraryModel.detail.lampMopa

                                Rectangle {
                                    height: 24
                                    width: mopaLabel.width + 16
                                    radius: 6
                                    visible: LibraryModel.detail.lampMopa
                                    color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.12)
                                    border.color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.3)
                                    border.width: 1
                                    Text {
                                        id: mopaLabel
                                        anchors.centerIn: parent
                                        text: "모자이크 제거"
                                        font.pixelSize: 13
                                        font.weight: Font.DemiBold
                                        color: Theme.accentNeon
                                    }
                                }

                                Repeater {
                                    model: (LibraryModel.detail.genresKo || "").split(",")

                                    delegate: Rectangle {
                                        id: genreChip
                                        height: 24
                                        width: genreLabel.width + 16
                                        radius: 6
                                        visible: {
                                            var t = modelData.trim()
                                            return t.length > 0 && t.indexOf("단축키") < 0
                                        }
                                        color: genreMa.containsMouse 
                                            ? Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.25)
                                            : Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.12)
                                        border.color: genreMa.containsMouse ? Theme.accentNeon : Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.3)
                                        border.width: 1
                                        scale: genreMa.containsMouse ? 1.05 : 1.0
                                        Behavior on scale { NumberAnimation { duration: 120 } }
                                        Behavior on color { ColorAnimation { duration: 120 } }

                                        Text {
                                            id: genreLabel
                                            anchors.centerIn: parent
                                            text: modelData.trim()
                                            font.pixelSize: 13
                                            font.weight: genreMa.containsMouse ? Font.Bold : Font.Normal
                                            color: Theme.accentNeon
                                        }

                                        MouseArea {
                                            id: genreMa
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.searchAndGoBack(modelData.trim())
                                        }
                                    }
                                }
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: Theme.spacingSm
                            visible: LibraryModel.detailEditing

                            Text {
                                text: LibraryModel.detail.productCode
                                font.pixelSize: 36
                                font.weight: Font.ExtraBold
                                color: Theme.accentNeon
                                width: parent.width
                                wrapMode: Text.WrapAnywhere
                            }

                            ActionButton {
                                text: "제목 · 다국어 편집…"
                                primary: false
                                onClicked: mlTitlePopup.open()
                            }

                            TextField {
                                id: edTitleKoQuick
                                width: parent.width
                                placeholderText: "제목 (한국어) 빠른 수정"
                                text: LibraryModel.editDraft.titleKo
                                color: Theme.textPrimary
                                font.pixelSize: 16
                                background: Rectangle {
                                    radius: 4
                                    color: Theme.bgSecondary
                                    border.color: Theme.glassBorder
                                    border.width: 1
                                }
                                onEditingFinished: LibraryModel.editDraft.titleKo = text
                            }

                            Row {
                                id: makerRow
                                width: parent.width
                                spacing: Theme.spacingSm
                                ActionButton {
                                    id: mkPickBtn
                                    text: "메이커 선택…"
                                    primary: false
                                    onClicked: {
                                        masterPickPopup.pickerMode = "maker"
                                        masterPickPopup.open()
                                    }
                                }
                                TextField {
                                    id: edMakerKo
                                    width: makerRow.width - mkPickBtn.width - makerRow.spacing
                                    placeholderText: "메이커 (한국어)"
                                    text: LibraryModel.editDraft.makerKo
                                    color: Theme.textPrimary
                                    font.pixelSize: 16
                                    background: Rectangle {
                                        radius: 4
                                        color: Theme.bgSecondary
                                        border.color: Theme.glassBorder
                                        border.width: 1
                                    }
                                    onEditingFinished: LibraryModel.editDraft.makerKo = text
                                }
                            }

                            Row {
                                id: relRow
                                width: parent.width
                                spacing: Theme.spacingSm
                                Text {
                                    id: relLbl
                                    text: "출시일"
                                    color: Theme.textMuted
                                    font.pixelSize: 13
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                TextField {
                                    id: edRelease
                                    width: relRow.width - relLbl.width - relRow.spacing
                                    placeholderText: "YYYY-MM-DD"
                                    text: LibraryModel.editDraft.releaseDate
                                    color: Theme.textPrimary
                                    font.pixelSize: 16
                                    background: Rectangle {
                                        radius: 4
                                        color: Theme.bgSecondary
                                        border.color: Theme.glassBorder
                                        border.width: 1
                                    }
                                    onEditingFinished: LibraryModel.editDraft.releaseDate = text
                                }
                            }

                            Row {
                                spacing: Theme.spacingSm
                                ActionButton {
                                    text: "장르 추가…"
                                    primary: false
                                    onClicked: {
                                        masterPickPopup.pickerMode = "genre"
                                        masterPickPopup.open()
                                    }
                                }
                                ActionButton {
                                    text: "배우 추가…"
                                    primary: false
                                    onClicked: {
                                        masterPickPopup.pickerMode = "actress"
                                        masterPickPopup.open()
                                    }
                                }
                            }

                            Flow {
                                width: parent.width
                                spacing: 6

                                Repeater {
                                    model: (LibraryModel.editDraft.genresKo || "").split(",")

                                    delegate: Rectangle {
                                        height: 24
                                        width: gChipLab.width + gChipX.width + 16
                                        radius: 4
                                        visible: chipText.length > 0
                                        property string chipText: modelData.trim()
                                        color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.12)
                                        border.color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.3)
                                        border.width: 1

                                        Row {
                                            anchors.centerIn: parent
                                            spacing: 4
                                            Text {
                                                id: gChipLab
                                                text: chipText
                                                font.pixelSize: 13
                                                color: Theme.accentNeon
                                            }
                                            Text {
                                                id: gChipX
                                                text: "✕"
                                                font.pixelSize: 13
                                                color: Theme.textMuted
                                                MouseArea {
                                                    anchors.fill: parent
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: LibraryModel.removeGenreChip(chipText)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Flow {
                                width: parent.width
                                spacing: 6

                                Repeater {
                                    model: (LibraryModel.editDraft.actorsKo || "").split(",")

                                    delegate: Rectangle {
                                        height: 24
                                        width: aChipLab.width + aChipX.width + 16
                                        radius: 4
                                        visible: chipText.length > 0
                                        property string chipText: modelData.trim()
                                        color: Qt.rgba(0.3, 0.6, 1.0, 0.12)
                                        border.color: Qt.rgba(0.3, 0.6, 1.0, 0.35)
                                        border.width: 1

                                        Row {
                                            anchors.centerIn: parent
                                            spacing: 4
                                            Text {
                                                id: aChipLab
                                                text: chipText
                                                font.pixelSize: 13
                                                color: Theme.textSecondary
                                            }
                                            Text {
                                                id: aChipX
                                                text: "✕"
                                                font.pixelSize: 13
                                                color: Theme.textMuted
                                                MouseArea {
                                                    anchors.fill: parent
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: LibraryModel.removeActorChip(chipText)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }


            // ── 파이프라인 상태 ────────────────────────
            GlassCard {
                width: parent.width
                height: 80

                Flow {
                    anchors.centerIn: parent
                    spacing: Theme.spacingXl
                    layoutDirection: Qt.LeftToRight

                    PipelineStage {
                        stageName: "Harvest"
                        status: {
                            var s = LibraryModel.detail.pipelineStage;
                            if (s === "none") return "pending";
                            return "done";
                        }
                    }

                    Text {
                        text: "\u27A1"
                        font.pixelSize: 20
                        color: Theme.textMuted
                        anchors.verticalCenter: undefined // Flow handles alignment differently or just don't anchor
                    }

                    PipelineStage {
                        stageName: "STT"
                        status: LibraryModel.detail.hasJaSrt ? "done" : "pending"
                    }

                    Text {
                        text: "\u27A1"
                        font.pixelSize: 20
                        color: Theme.textMuted
                    }

                    PipelineStage {
                        stageName: "Subtitle"
                        status: LibraryModel.detail.hasKoSrt ? "done" : "pending"
                    }

                    Text {
                        text: "\u27A1"
                        font.pixelSize: 20
                        color: Theme.textMuted
                    }

                    PipelineStage {
                        stageName: "자체자막"
                        status: LibraryModel.detail.lampHardcoded ? "done" : "pending"
                    }

                    Text {
                        text: "\u27A1"
                        font.pixelSize: 20
                        color: Theme.textMuted
                    }

                    PipelineStage {
                        stageName: "모자이크 제거"
                        status: LibraryModel.detail.lampMopa ? "done" : "pending"
                    }
                }
            }

            // ── 시놉시스 ──────────────────────────────
            GlassCard {
                visible: LibraryModel.detailEditing || LibraryModel.detail.synopsisKo !== ""
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Row {
                        spacing: 8
                        Rectangle {
                            width: 3; height: synopsisTitle.height
                            color: Theme.accentNeon
                            radius: 2
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: synopsisTitle
                            text: "시놉시스"
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                    }

                    SelectableText {
                        visible: !LibraryModel.detailEditing
                        text: LibraryModel.detail.synopsisKo
                        font.pixelSize: Theme.fontBody
                        color: Theme.textSecondary
                        width: parent.width
                        wrapMode: TextEdit.Wrap
                    }

                    Column {
                        visible: LibraryModel.detailEditing
                        width: parent.width
                        spacing: Theme.spacingSm

                        ActionButton {
                            text: "시놉시스 · 다국어 편집…"
                            primary: false
                            onClicked: {
                                mlSynopsisPopup.editMode = "synopsis"
                                mlSynopsisPopup.open()
                            }
                        }

                        TextArea {
                            id: edSynKoQuick
                            width: parent.width
                            height: Math.min(300, Math.max(150, implicitHeight))
                            placeholderText: "시놉시스 (한국어)"
                            text: LibraryModel.editDraft.synopsisKo
                            wrapMode: TextArea.Wrap
                            selectByMouse: true
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            background: Rectangle {
                                radius: 4
                                color: Theme.bgSecondary
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            onTextChanged: LibraryModel.editDraft.synopsisKo = text
                        }
                    }
                }
            }

            // ── 번역 노트 (작품 + 배우) ─────────────────
            GlassCard {
                visible: LibraryModel.detailEditing
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Row {
                        spacing: Theme.spacingSm
                        Rectangle {
                            width: 3; height: noteTitleText.height
                            color: Theme.accentNeon
                            radius: 2
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: noteTitleText
                            text: "번역 노트"
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                    }

                    Text {
                        text: "작품 노트(이 작품 한정) + 배우 노트(같은 배우의 모든 작품 공통)는 전역 노트와 함께 Gemini 번역 프롬프트의 {{note}}에 합쳐 주입됩니다."
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        wrapMode: Text.Wrap
                        width: parent.width
                    }

                    Row {
                        spacing: Theme.spacingSm
                        ActionButton {
                            text: "작품 노트 자동 생성"
                            primary: false
                            enabled: !LibraryModel.translationNoteGenerating
                            onClicked: LibraryModel.generateWorkTranslationNote(LibraryModel.editDraft.productCode)
                        }
                        ActionButton {
                            text: LibraryModel.editDraft.actressNoteTargetJa.length > 0
                                ? ("배우 노트 자동 생성 (" + LibraryModel.editDraft.actressNoteTargetJa + ")")
                                : "배우 노트 자동 생성"
                            primary: false
                            enabled: !LibraryModel.translationNoteGenerating
                                     && LibraryModel.editDraft.actressNoteTargetJa.length > 0
                            onClicked: LibraryModel.generateActressTranslationNote(LibraryModel.editDraft.actressNoteTargetJa)
                        }
                        Text {
                            visible: LibraryModel.translationNoteGenerating
                            text: "Gemini 노트 생성 중…"
                            font.pixelSize: Theme.fontCaption
                            color: Theme.accentNeon
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // 작품 노트
                    Text {
                        text: "작품 노트"
                        font.pixelSize: Theme.fontBody
                        color: Theme.textSecondary
                    }
                    Rectangle {
                        width: parent.width
                        height: 240
                        radius: Theme.radiusSm
                        color: Theme.surfaceLight
                        border.color: workNoteArea.activeFocus ? Theme.accentNeon : Theme.glassBorder
                        border.width: 1
                        AppScrollView {
                            anchors.fill: parent
                            anchors.margins: 4
                            clip: true
                            TextArea {
                                id: workNoteArea
                                width: parent.width
                                placeholderText: "[작품 기본 컨텍스트]\n- 핵심 장르: ...\n- 전체 톤앤매너: ...\n\n[화자 프로필 및 관계]\n- 남성 (상사): 반말. 거만/명령조.\n- 여성 (부하직원): 존댓말. 후반 무너지는 말투.\n\n[Whisper AI 오인식 교정 사전]\n- (잘못된 인식) -> (올바른 단어/상황)\n\n[용어/은어 매핑]\n- 원어 => 번역어"
                                text: LibraryModel.editDraft.translationNote
                                onTextChanged: LibraryModel.editDraft.translationNote = text
                                wrapMode: TextArea.Wrap
                                selectByMouse: true
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontBody
                                background: null
                            }
                        }
                    }

                    // 배우 노트
                    Text {
                        text: LibraryModel.editDraft.actressNoteTargetJa.length > 0
                            ? ("배우 노트 (" + LibraryModel.editDraft.actressNoteTargetJa + ")")
                            : "배우 노트 (배우 미지정 — 편집 불가)"
                        font.pixelSize: Theme.fontBody
                        color: Theme.textSecondary
                    }
                    Rectangle {
                        width: parent.width
                        height: 180
                        radius: Theme.radiusSm
                        color: Theme.surfaceLight
                        border.color: actressNoteArea.activeFocus ? Theme.accentNeon : Theme.glassBorder
                        border.width: 1
                        opacity: LibraryModel.editDraft.actressNoteTargetJa.length > 0 ? 1.0 : 0.5
                        AppScrollView {
                            anchors.fill: parent
                            anchors.margins: 4
                            clip: true
                            TextArea {
                                id: actressNoteArea
                                width: parent.width
                                enabled: LibraryModel.editDraft.actressNoteTargetJa.length > 0
                                placeholderText: "[화자 프로필]\n- 평소 말투/페르소나\n\n[고정 표기/호칭 사전]\n- 원어 => 번역어"
                                text: LibraryModel.editDraft.actressTranslationNote
                                onTextChanged: LibraryModel.editDraft.actressTranslationNote = text
                                wrapMode: TextArea.Wrap
                                selectByMouse: true
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontBody
                                background: null
                            }
                        }
                    }
                }
            }

            // ── Grok 씬 요약 ──────────────────────────
            GlassCard {
                id: grokScenesCard
                property var scenesData: {
                    try { return JSON.parse(LibraryModel.detail.grokScenesJson || "[]") }
                    catch(e) { return [] }
                }
                visible: LibraryModel.detailEditing || scenesData.length > 0
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingMd

                    // 헤더
                    Row {
                        spacing: 8
                        Rectangle {
                            width: 3; height: grokTitle.height
                            color: "#a78bfa"
                            radius: 2
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: grokTitle
                            text: "씬 분석 (Grok)" + (LibraryModel.detail.grokVerified ? "" : " · 미검증")
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: LibraryModel.detailEditing
                                  ? (LibraryModel.sceneEdit.entryCount() + "개 씬 · 편집")
                                  : (grokScenesCard.scenesData.length + "개 씬")
                            font.pixelSize: Theme.fontCaption
                            color: "#a78bfa"
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // 읽기 전용 씬 카드
                    Column {
                        width: parent.width
                        spacing: 10
                        visible: !LibraryModel.detailEditing

                        Repeater {
                            model: grokScenesCard.scenesData

                            delegate: Rectangle {
                                width: parent.width
                                height: sceneContent.height + 24
                                radius: Theme.radiusMd
                                color: Qt.rgba(255,255,255,0.04)
                                border.color: Qt.rgba(167/255, 139/255, 250/255, 0.18)
                                border.width: 1

                                Rectangle {
                                    anchors.top: parent.top
                                    anchors.left: parent.left
                                    anchors.topMargin: 12
                                    anchors.leftMargin: 14
                                    width: 28; height: 20
                                    radius: 4
                                    color: Qt.rgba(167/255, 139/255, 250/255, 0.25)

                                    Text {
                                        anchors.centerIn: parent
                                        text: "S" + (index + 1)
                                        font.pixelSize: 12
                                        font.weight: Font.Bold
                                        color: "#a78bfa"
                                    }
                                }

                                Column {
                                    id: sceneContent
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 12
                                    anchors.leftMargin: 52
                                    spacing: 5

                                    Row {
                                        spacing: 10

                                        SelectableText {
                                            text: modelData["scene_label"] || ""
                                            font.pixelSize: Theme.fontBody
                                            font.weight: Font.DemiBold
                                            color: "#e2d9fa"
                                            visible: text !== ""
                                        }

                                        SelectableText {
                                            text: modelData["time_range"] || ""
                                            font.pixelSize: Theme.fontCaption
                                            color: Qt.rgba(167/255, 139/255, 250/255, 0.7)
                                            anchors.verticalCenter: parent.verticalCenter
                                            visible: text !== ""
                                        }
                                    }

                                    SelectableText {
                                        text: modelData["scene_summary"] || ""
                                        font.pixelSize: 15
                                        color: Qt.rgba(255,255,255,0.72)
                                        width: parent.width
                                        wrapMode: TextEdit.Wrap
                                        visible: text !== ""
                                    }
                                }
                            }
                        }
                    }

                    // 편집 모드 씬 목록
                    Column {
                        width: parent.width
                        spacing: Theme.spacingSm
                        visible: LibraryModel.detailEditing

                        Row {
                            spacing: Theme.spacingSm
                            ActionButton {
                                text: "씬 추가"
                                primary: false
                                onClicked: LibraryModel.sceneEdit.appendEmptyRow()
                            }
                            ActionButton {
                                text: "씬만 저장 (DB 메타 제외)"
                                primary: false
                                onClicked: LibraryModel.saveSceneEditsOnly()
                            }
                        }

                        Label {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            text: "구간 예: 00:01:30 ~ 00:05:00 — 변경 시 해당 씬 스틸 경로는 비워지고 재추출이 필요할 수 있습니다."
                            font.pixelSize: Theme.fontCaption - 1
                            color: Theme.textMuted
                        }

                        AppScrollView {
                            width: parent.width
                            height: 400
                            clip: true

                            ListView {
                                boundsBehavior: Theme.boundsBehavior
                                id: sceneEditList
                                width: parent.width
                                height: contentHeight
                                spacing: 10
                                model: LibraryModel.sceneEdit

                                delegate: Rectangle {
                                    width: ListView.view.width
                                    implicitHeight: sceneEditCol.implicitHeight + 20
                                    radius: Theme.radiusMd
                                    color: Qt.rgba(255,255,255,0.05)
                                    border.color: Qt.rgba(167/255, 139/255, 250/255, 0.28)
                                    border.width: 1

                                    Column {
                                        id: sceneEditCol
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: 10
                                        spacing: 6

                                        Row {
                                            width: parent.width
                                            spacing: 8
                                            Text {
                                                text: "#" + (index + 1)
                                                color: "#a78bfa"
                                                font.bold: true
                                                anchors.verticalCenter: parent.verticalCenter
                                            }
                                            Item { width: parent.width - delBtn.width - 40; height: 1 }
                                            ActionButton {
                                                id: delBtn
                                                text: "삭제"
                                                primary: false
                                                onClicked: LibraryModel.sceneEdit.removeRowAt(index)
                                            }
                                        }

                                        Label { text: "scene_id"; font.pixelSize: 13; color: Theme.textMuted }
                                        TextField {
                                            width: parent.width
                                            text: sceneId
                                            placeholderText: "scene_id"
                                            color: Theme.textPrimary
                                            font.pixelSize: 15
                                            background: Rectangle {
                                                radius: 4
                                                color: Theme.bgSecondary
                                                border.color: Theme.glassBorder
                                                border.width: 1
                                            }
                                            onEditingFinished: LibraryModel.sceneEdit.setField(index, "sceneId", text)
                                        }

                                        Label { text: "시간 구간 time_range"; font.pixelSize: 13; color: Theme.textMuted }
                                        TextField {
                                            width: parent.width
                                            text: timeRange
                                            placeholderText: "00:00:00 ~ 00:10:00"
                                            color: Theme.textPrimary
                                            font.pixelSize: 15
                                            background: Rectangle {
                                                radius: 4
                                                color: Theme.bgSecondary
                                                border.color: Theme.glassBorder
                                                border.width: 1
                                            }
                                            onEditingFinished: LibraryModel.sceneEdit.setField(index, "timeRange", text)
                                        }

                                        Label { text: "라벨"; font.pixelSize: 13; color: Theme.textMuted }
                                        TextField {
                                            width: parent.width
                                            text: sceneLabel
                                            color: Theme.textPrimary
                                            font.pixelSize: 15
                                            background: Rectangle {
                                                radius: 4
                                                color: Theme.bgSecondary
                                                border.color: Theme.glassBorder
                                                border.width: 1
                                            }
                                            onEditingFinished: LibraryModel.sceneEdit.setField(index, "sceneLabel", text)
                                        }

                                        Label { text: "요약"; font.pixelSize: 13; color: Theme.textMuted }
                                        TextArea {
                                            width: parent.width
                                            height: Math.min(150, Math.max(70, implicitHeight))
                                            text: sceneSummary
                                            wrapMode: TextArea.Wrap
                                            selectByMouse: true
                                            color: Theme.textPrimary
                                            font.pixelSize: 15
                                            background: Rectangle {
                                                radius: 4
                                                color: Theme.bgSecondary
                                                border.color: Theme.glassBorder
                                                border.width: 1
                                            }
                                            onEditingFinished: LibraryModel.sceneEdit.setField(index, "sceneSummary", text)
                                        }

                                        Label { text: "톤 · 태그(쉼표)"; font.pixelSize: 13; color: Theme.textMuted }
                                        Row {
                                            width: parent.width
                                            spacing: 6
                                            TextField {
                                                width: (parent.width - 6) / 2
                                                text: tone
                                                placeholderText: "tone"
                                                color: Theme.textPrimary
                                                font.pixelSize: 15
                                                background: Rectangle {
                                                    radius: 4
                                                    color: Theme.bgSecondary
                                                    border.color: Theme.glassBorder
                                                    border.width: 1
                                                }
                                                onEditingFinished: LibraryModel.sceneEdit.setField(index, "tone", text)
                                            }
                                            TextField {
                                                width: (parent.width - 6) / 2
                                                text: keyTags
                                                placeholderText: "tag1, tag2"
                                                color: Theme.textPrimary
                                                font.pixelSize: 15
                                                background: Rectangle {
                                                    radius: 4
                                                    color: Theme.bgSecondary
                                                    border.color: Theme.glassBorder
                                                    border.width: 1
                                                }
                                                onEditingFinished: LibraryModel.sceneEdit.setField(index, "keyTags", text)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── 미디어 폴더 연결 ───────────────────────
            GlassCard {
                id: folderMediaCard
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Row {
                        spacing: 8
                        Rectangle {
                            width: 3; height: folderSectionTitle.height
                            color: Theme.accentNeon
                            radius: 2
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: folderSectionTitle
                            text: "미디어 폴더"
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                    }

                    SelectableText {
                        text: LibraryModel.detail.folderPath !== ""
                              ? LibraryModel.detail.folderPath
                              : "미연결 — 라이브러리 작품 폴더 · MEDIA_ROOT 순으로 영상을 찾습니다."
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textSecondary
                        width: parent.width
                        wrapMode: TextEdit.Wrap
                    }

                    Flow {
                        width: parent.width
                        spacing: Theme.spacingSm

                        ActionButton {
                            id: folderBindBtn
                            text: "폴더 연결"
                            primary: true
                            focusPolicy: Qt.StrongFocus
                            onClicked: {
                                root.folderBindMode = "normal"
                                root.openFolderPicker()
                            }
                            Keys.onPressed: function (event) {
                                event.accepted = root.handleFolderRowKey(event, 0)
                            }
                        }

                        ActionButton {
                            id: folderForceBtn
                            text: "강제 연결"
                            primary: false
                            focusPolicy: Qt.StrongFocus
                            onClicked: {
                                root.folderBindMode = "force"
                                root.openFolderPicker()
                            }
                            Keys.onPressed: function (event) {
                                event.accepted = root.handleFolderRowKey(event, 1)
                            }
                        }

                        ActionButton {
                            id: folderClearBtn
                            text: "연결 해제"
                            primary: false
                            focusPolicy: Qt.StrongFocus
                            enabled: LibraryModel.detail.folderPath !== ""
                            onClicked: LibraryModel.clearFolderBinding(LibraryModel.detail.productCode)
                            Keys.onPressed: function (event) {
                                event.accepted = root.handleFolderRowKey(event, 2)
                            }
                        }

                        ActionButton {
                            id: folderOpenBtn
                            text: "폴더 열기"
                            primary: false
                            focusPolicy: Qt.StrongFocus
                            onClicked: LibraryModel.openFolder(LibraryModel.detail.productCode)
                            Keys.onPressed: function (event) {
                                event.accepted = root.handleFolderRowKey(event, 3)
                            }
                        }
                    }
                }
            }

            // ── 스냅샷 갤러리 ─────────────────────────
            GlassCard {
                visible: LibraryModel.detail.stillPaths.length > 0 || LibraryModel.isExtractingSnapshots
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingMd

                    Row {
                        spacing: 8
                        Rectangle {
                            width: 3; height: snapTitle.height
                            color: "#38bdf8"
                            radius: 2
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: snapTitle
                            text: "스냅샷"
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            id: snapshotProgressText
                            text: LibraryModel.isExtractingSnapshots ? LibraryModel.snapshotProgressMsg : (LibraryModel.detail.stillPaths.length + "장")
                            font.pixelSize: Theme.fontCaption
                            color: LibraryModel.isExtractingSnapshots ? Theme.accentNeon : "#38bdf8"
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Item { width: 10 }

                        // 다이제스트 영상 추출 버튼
                        ActionButton {
                            text: LibraryModel.isGeneratingDigest ? "⏳ 렌더링 중... " + LibraryModel.digestProgress + "%" : "다이제스트 생성"
                            height: 28
                            enabled: !LibraryModel.isGeneratingDigest // 작업 중일 때 비활성화
                            visible: (LibraryModel.detail.videoPath !== "" && LibraryModel.detail.digestPath === "") || LibraryModel.isGeneratingDigest
                            clip: true

                            // 버튼 내부에서 차오르는 프로그레스 뷰
                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                width: parent.width * (LibraryModel.digestProgress / 100.0)
                                color: Qt.rgba(56/255, 189/255, 248/255, 0.35) // 테마(스카이블루) 기반 반투명 색상
                                visible: LibraryModel.isGeneratingDigest
                                Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutQuad } }
                            }

                            onClicked: {
                                LibraryModel.generateDigest(LibraryModel.detail.productCode, LibraryModel.detail.videoPath)
                            }
                        }

                        // 수동 추출 버튼
                        ActionButton {
                            text: "스냅샷 재생성"
                            height: 28
                            primary: false
                            visible: LibraryModel.detail.videoPath !== ""
                            onClicked: LibraryModel.generateSnapshots(LibraryModel.detail.productCode, LibraryModel.detail.videoPath)
                        }
                    }

                    // 스냅샷 갤러리: FocusScope 로 키보드 포커스 분리(GridView interactive 는 스크롤 위임용 false 유지)
                    // GlassCard 높이는 childrenRect 인데 FocusScope 기본 높이가 0이라 격자가 안 보였음 → snapGrid 높이와 맞춤
                    FocusScope {
                        id: snapFocusScope
                        width: parent.width
                        height: snapGrid.height
                        focus: false
                        focusPolicy: Qt.StrongFocus
                        Keys.onPressed: function (event) {
                            event.accepted = root.processSnapNavigationKey(event.key, event.modifiers)
                        }

                        GridView {
                            boundsBehavior: Theme.boundsBehavior
                            id: snapGrid
                            z: 1
                            anchors.top: parent.top
                            width: parent.width
                            focusPolicy: Qt.NoFocus
                            currentIndex: root.snapFocusIdx
                            highlightFollowsCurrentItem: true
                            highlightMoveDuration: 0
                            highlight: Item {
                                width: snapGrid.cellWidth
                                height: snapGrid.cellHeight
                                visible: root.detailRegion === "snap"
                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    radius: Theme.radiusSm
                                    color: "transparent"
                                    border.color: Theme.accentNeon
                                    border.width: 3
                                }
                            }
                            // QVariantList/model 에는 .length 가 없어 NaN 높이 → 갤러리가 안 보이던 문제
                            height: {
                                var n = LibraryModel.detail.stillPaths.length
                                if (cols <= 0 || n <= 0)
                                    return 0
                                return Math.ceil(n / cols) * cellHeight
                            }

                            property int cols: Math.max(3, Math.floor(width / 180))
                            cellWidth: Math.floor(width / cols)
                            cellHeight: Math.round(cellWidth * 9 / 16) + 12

                            interactive: false
                            keyNavigationEnabled: false
                            model: LibraryModel.detail.stillPaths

                            delegate: Item {
                                width: snapGrid.cellWidth
                                height: snapGrid.cellHeight

                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    radius: Theme.radiusSm
                                    color: Qt.rgba(0,0,0,0.35)
                                    clip: true
                                    border.color: Qt.rgba(56/255, 189/255, 248/255, 0.15)
                                    border.width: 1

                                    Image {
                                        anchors.fill: parent
                                        source: Theme.pathToUrl(modelData)
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true

                                        Rectangle {
                                            anchors.fill: parent
                                            color: Qt.rgba(0,0,0,0.3)
                                            visible: parent.status === Image.Loading
                                        }
                                    }

                                    // 명시적인 포커스 하이라이트 (스냅 모드일 때만 활성화)
                                    Rectangle {
                                        anchors.fill: parent
                                        anchors.margins: 4
                                        radius: Theme.radiusSm
                                        color: "transparent"
                                        border.color: Theme.accentNeon
                                        border.width: (root.detailRegion === "snap" && root.snapFocusIdx === index) ? 4 : 0
                                        visible: root.detailRegion === "snap" && root.snapFocusIdx === index
                                        z: 2
                                    }

                                    Rectangle {
                                        id: hoverOverlay
                                        anchors.fill: parent
                                        radius: Theme.radiusSm
                                        color: itemMouse.containsMouse ? Qt.rgba(56/255, 189/255, 248/255, 0.18) : "transparent"
                                        border.color: itemMouse.containsMouse ? Qt.rgba(56/255, 189/255, 248/255, 0.7) : "transparent"
                                        border.width: 2
                                        Behavior on color { ColorAnimation { duration: 100 } }

                                        Text {
                                            anchors.centerIn: parent
                                            text: "🔍"
                                            font.pixelSize: 22
                                            visible: itemMouse.containsMouse
                                        }
                                    }

                                    MouseArea {
                                        id: itemMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            root.detailRegion = "snap"
                                            root.snapFocusIdx = index
                                            lightboxOverlay.coverMode = false
                                            lightboxOverlay.currentIndex = index
                                            lightboxImage.source = Theme.pathToUrl(modelData)
                                            lightboxOverlay.visible = true
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 하단 여백
            Item { height: Theme.spacingLg }
        }
    }

    Connections {
        target: mainScroll.contentItem
        function onContentYChanged() {
            /// 휠 스크롤 후 내부 Flickable이 포커스를 가져가면 방향키가 스크롤만 먹고 Keys/Shortcut이 안 먹음 → browse 모드에서 루트로 복귀
            if (root.detailRegion === "none" || root.detailRegion === "cover") {
                Qt.callLater(function () {
                    root.forceActiveFocus()
                })
            }
        }
    }

    Connections {
        target: mainScroll
        function onContentItemChanged() {
            scrollFocusFixTimer.start()
        }
    }

    MultiLangEditorPopup {
        id: mlTitlePopup
        editMode: "title"
    }

    MultiLangEditorPopup {
        id: mlSynopsisPopup
        editMode: "synopsis"
    }

    MasterSearchPopup {
        id: masterPickPopup
    }

    SimilarProductsPopup {
        id: similarPopup
        onProductClicked: function(sku) {
            LibraryModel.loadDetail(sku)
        }

    }

    Connections {
        target: LibraryModel
        function onDetailEditingChanged() {
            if (!LibraryModel.detailEditing)
                return
            edTitleKoQuick.text = LibraryModel.editDraft.titleKo
            edMakerKo.text = LibraryModel.editDraft.makerKo
            edRelease.text = LibraryModel.editDraft.releaseDate
            edSynKoQuick.text = LibraryModel.editDraft.synopsisKo
        }

        function onSimilarProductsReady(results) {
            similarPopup.isLoading = false
            similarPopup.model = results
        }
    }

    // ── 키보드 도움말 (F1) ───────────────────────────────
    Item {
        id: keyboardHelpLayer
        anchors.fill: parent
        visible: root.keyboardHelpVisible
        z: 101

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.45)
            MouseArea {
                anchors.fill: parent
                onClicked: root.keyboardHelpVisible = false
            }
        }

        Rectangle {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: Theme.spacingXl
            width: Math.min(320, parent.width - Theme.spacingXl * 2)
            radius: Theme.radiusMd
            color: Theme.surface
            border.color: Theme.glassBorder
            border.width: 1

            Column {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingSm

                Text {
                    text: "키보드 단축키"
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                    width: parent.width
                }

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textSecondary
                    lineHeight: 1.38
                    text: {
                        root.detailRegion
                        root.keyboardHelpVisible
                        lightboxOverlay.visible
                        lightboxOverlay.coverMode
                        lightboxOverlay.allViewMode
                        return root.keyboardHelpLines().join("\n")
                    }
                }

                Text {
                    text: "바깥을 클릭하거나 Esc로 닫기"
                    font.pixelSize: Theme.fontCaption - 1
                    color: Theme.textMuted
                    width: parent.width
                }
            }
        }
    }
}