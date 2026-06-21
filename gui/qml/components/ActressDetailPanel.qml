import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

Item {
    id: root

    property var actressModel: null
    property bool isEditMode: false
    property bool _suppressSave: false

    signal back()
    signal requestMerge()

    property var _allWorks: []
    property string selectedGenreFilter: ""
    property string worksSortKey: "release_date"
    property bool worksSortAscending: false

    readonly property var _worksSortOptions: [
        { key: "product_code", label: "품번" },
        { key: "release_date", label: "출시일" },
        { key: "favorite_score", label: "좋아요" },
        { key: "user_rating", label: "내 점수" }
    ]

    function formatDebut(d) {
        if (!d) return "-"
        var s = String(d)
        return s.length >= 7 ? s.substring(0, 7) : s
    }

    function ageFromBirthDate(birthStr) {
        if (!birthStr) return -1
        var s = String(birthStr).trim()
        if (s.length < 7 || s[4] !== "-") return -1
        var y = parseInt(s.substring(0, 4), 10)
        var m = parseInt(s.substring(5, 7), 10)
        var d = s.length >= 10 ? parseInt(s.substring(8, 10), 10) : 1
        if (isNaN(y) || isNaN(m) || isNaN(d)) return -1

        var today = new Date()
        var age = today.getFullYear() - y
        var monthDiff = (today.getMonth() + 1) - m
        var dayDiff = today.getDate() - d
        if (monthDiff < 0 || (monthDiff === 0 && dayDiff < 0))
            age--
        if (age < 0 || age > 150) return -1
        return age
    }

    function formatAgeLabel(birthStr) {
        var age = ageFromBirthDate(birthStr)
        return age >= 0 ? ("나이 " + age + "세") : ""
    }

    function normalizeCupSize(raw) {
        if (raw === undefined || raw === null) return ""
        var s = String(raw).trim()
        if (!s) return ""
        s = s.replace(/cup/gi, "").replace(/컵/g, "").trim()
        if (!s) return ""
        var ch = s.charAt(0)
        if (ch >= "a" && ch <= "z") return ch.toUpperCase()
        if (ch >= "A" && ch <= "Z") return ch
        return ""
    }

    function formatCupSize(raw) {
        var letter = normalizeCupSize(raw)
        return letter ? (letter + "컵") : "-"
    }

    function _saveEdit() {
        if (!actressModel || !actressModel.currentProfile.id) return
        var data = {
            name_ko:      editNameKo.text.trim(),
            name_ja:      editNameJa.text.trim(),
            romaji:       editRomaji.text.trim() || null,
            birth_date:   editBirthDate.text.trim() || null,
            height:       editHeight.text.trim() ? parseInt(editHeight.text, 10) : null,
            bust:         editBust.text.trim() ? parseInt(editBust.text, 10) : null,
            waist:        editWaist.text.trim() ? parseInt(editWaist.text, 10) : null,
            hip:          editHip.text.trim() ? parseInt(editHip.text, 10) : null,
            cup_size:     root.normalizeCupSize(editCupSize.text) || null,
            debut_date:   editDebutDate.text.trim() || null,
            agency:       editAgency.text.trim() || null,
            profile_text: profileTextArea.text.trim() || null,
        }
        actressModel.updateProfile(actressModel.currentProfile.id, data)
        root.isEditMode = false
    }

    function _enterEdit() {
        if (!actressModel || !actressModel.currentProfile.id) return
        var p = actressModel.currentProfile
        editNameKo.text = p.name_ko || ""
        editNameJa.text = p.name_ja || ""
        editRomaji.text = p.romaji || ""
        editBirthDate.text = p.birth_date || ""
        editHeight.text = p.height ? String(p.height) : ""
        editBust.text = p.bust ? String(p.bust) : ""
        editWaist.text = p.waist ? String(p.waist) : ""
        editHip.text = p.hip ? String(p.hip) : ""
        editCupSize.text = root.normalizeCupSize(p.cup_size)
        editDebutDate.text = p.debut_date_raw || p.debut_date || ""
        editAgency.text = p.agency || ""
        root.isEditMode = true
    }

    function _genreMatches(work, genre) {
        if (!genre) return true
        var raw = (work.genres_ko || "").trim()
        if (!raw) return false
        var parts = raw.split(",")
        for (var i = 0; i < parts.length; i++) {
            if (parts[i].trim() === genre) return true
        }
        return false
    }

    function _workRating(w) {
        return (w.user_rating || w.userRating || 0)
    }

    function _workFavorite(w) {
        return (w.favorite_score || 0)
    }

    function _filteredHasAnyRating(items) {
        for (var i = 0; i < items.length; i++) {
            if (_workRating(items[i]) > 0)
                return true
        }
        return false
    }

    function _compareWorks(a, b, anyUserRating) {
        var dir = worksSortAscending ? 1 : -1
        if (worksSortKey === "product_code") {
            return dir * String(a.product_code || "").localeCompare(String(b.product_code || ""), "ko")
        }
        if (worksSortKey === "release_date") {
            return dir * String(a.release_date || "").localeCompare(String(b.release_date || ""))
        }
        if (worksSortKey === "favorite_score") {
            return dir * (_workFavorite(a) - _workFavorite(b))
        }
        if (worksSortKey === "user_rating") {
            if (!anyUserRating)
                return dir * (_workFavorite(a) - _workFavorite(b))

            var ra = _workRating(a)
            var rb = _workRating(b)
            var aHas = ra > 0
            var bHas = rb > 0

            if (aHas && bHas) {
                var cmp = ra - rb
                if (cmp !== 0)
                    return dir * cmp
                return dir * (_workFavorite(a) - _workFavorite(b))
            }
            if (aHas !== bHas)
                return aHas ? -1 : 1
            return dir * (_workFavorite(a) - _workFavorite(b))
        }
        return 0
    }

    function _workListRow(w) {
        return {
            product_code: String(w.product_code || ""),
            title_ko: String(w.title_ko || w.titleKo || ""),
            titleKo: String(w.title_ko || w.titleKo || ""),
            actors_ko: String(w.actors_ko || w.actorsKo || ""),
            actorsKo: String(w.actors_ko || w.actorsKo || ""),
            genres_ko: String(w.genres_ko || ""),
            cover_path: String(w.cover_path || w.coverPath || ""),
            coverPath: String(w.cover_path || w.coverPath || ""),
            release_date: String(w.release_date || ""),
            favorite_score: Number(w.favorite_score || 0),
            user_rating: Number(w.user_rating || w.userRating || 0),
            userRating: Number(w.user_rating || w.userRating || 0),
            user_liked: Boolean(w.user_liked || false)
        }
    }

    function _rebuildWorksList() {
        worksListModel.clear()
        var filtered = []
        for (var i = 0; i < _allWorks.length; i++) {
            if (_genreMatches(_allWorks[i], selectedGenreFilter))
                filtered.push(_allWorks[i])
        }
        var anyUserRating = _filteredHasAnyRating(filtered)
        filtered.sort(function(a, b) { return _compareWorks(a, b, anyUserRating) })
        for (var j = 0; j < filtered.length; j++)
            worksListModel.append(_workListRow(filtered[j]))
    }

    function setGenreFilter(genre) {
        selectedGenreFilter = (selectedGenreFilter === genre) ? "" : genre
        _rebuildWorksList()
    }

    function toggleWorksSort(key) {
        if (worksSortKey === key)
            worksSortAscending = !worksSortAscending
        else {
            worksSortKey = key
            worksSortAscending = (key === "product_code")
        }
        _rebuildWorksList()
    }

    function refreshWorksAndGenres() {
        worksListModel.clear()
        workGenresModel.clear()
        _allWorks = []
        selectedGenreFilter = ""
        worksSortKey = "release_date"
        worksSortAscending = false
        if (!actressModel || !actressModel.currentProfile.id) return
        var id = actressModel.currentProfile.id
        var works = actressModel.getLibraryWorks(id)
        _allWorks = works.slice()
        _rebuildWorksList()
        var genres = actressModel.getWorkGenres(id)
        for (var j = 0; j < genres.length; j++)
            workGenresModel.append({ "name": genres[j] })
    }

    Connections {
        target: root.actressModel
        function onCurrentProfileChanged() {
            root.isEditMode = false
            root._suppressSave = true
            if (root.actressModel)
                profileTextArea.text = root.actressModel.currentProfile.profile_text || ""
            root._suppressSave = false
            root.refreshWorksAndGenres()
        }
    }

    Timer {
        id: intensityTimer
        interval: 500
        onTriggered: {
            if (actressModel && actressModel.currentProfile.id)
                actressModel.updateProfile(actressModel.currentProfile.id,
                    { "favorite_intensity": intensitySlider.value })
        }
    }

    Timer {
        id: profileTextTimer
        interval: 1000
        onTriggered: {
            if (actressModel && actressModel.currentProfile.id)
                actressModel.updateProfile(actressModel.currentProfile.id,
                    { "profile_text": profileTextArea.text })
        }
    }

    FileDialog {
        id: profileFileDialog
        title: "대표 사진 선택"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["이미지 파일 (*.jpg *.jpeg *.png *.webp *.bmp)"]
        onAccepted: {
            var id = actressModel ? actressModel.currentProfile.id : 0
            if (!id) return
            for (var i = 0; i < selectedFiles.length; i++)
                actressModel.addImage(id, profileFileDialog.selectedFiles[i], true)
        }
    }

    FileDialog {
        id: galleryFileDialog
        title: "갤러리 사진 선택"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["이미지 파일 (*.jpg *.jpeg *.png *.webp *.bmp)"]
        onAccepted: {
            var id = actressModel ? actressModel.currentProfile.id : 0
            if (!id) return
            for (var i = 0; i < selectedFiles.length; i++)
                actressModel.addImage(id, galleryFileDialog.selectedFiles[i], false)
        }
    }

    function _localPaths(urls) {
        var out = []
        for (var i = 0; i < urls.length; i++) {
            var u = urls[i]
            if (u && u.toLocalFile)
                out.push(u.toLocalFile())
            else {
                var s = String(u)
                if (s.indexOf("file:///") === 0)
                    s = decodeURIComponent(s.substring(8))
                else if (s.indexOf("file://") === 0)
                    s = decodeURIComponent(s.substring(7))
                out.push(s)
            }
        }
        return out
    }

    function _uploadPaths(paths, isProfile) {
        var id = actressModel ? actressModel.currentProfile.id : 0
        if (!id) return
        for (var i = 0; i < paths.length; i++)
            actressModel.addImage(id, paths[i], isProfile && i === 0)
    }

    ListModel { id: worksListModel }
    ListModel { id: workGenresModel }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 상단 바 (고정)
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            ActionButton {
                text: "← 목록"
                onClicked: root.back()
            }

            Text {
                text: (actressModel && actressModel.currentProfile.name_ko) || "배우 상세"
                font.pixelSize: Theme.fontSubtitle
                font.bold: true
                color: Theme.textPrimary
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            ActionButton {
                visible: !root.isEditMode
                text: "편집"
                onClicked: root._enterEdit()
            }
            ActionButton {
                visible: root.isEditMode
                text: "저장"
                primary: true
                onClicked: root._saveEdit()
            }
            ActionButton {
                visible: root.isEditMode
                text: "취소"
                onClicked: root.isEditMode = false
            }
            ActionButton {
                text: "배우 합치기"
                onClicked: root.requestMerge()
            }
        }

        AppScrollView {
            id: detailScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true

            Column {
                width: detailScroll.availableWidth
                spacing: Theme.spacingLg
                bottomPadding: Theme.spacingLg

                // 사진 + 갤러리
                Item {
                    width: parent.width - Theme.spacingMd * 2
                    x: Theme.spacingMd
                    height: actressGallery.implicitHeight

                    ActressGallery {
                        id: actressGallery
                        width: parent.width
                        actressNameKo: (actressModel && actressModel.currentProfile.name_ko) || ""
                        profileImageUrl: actressModel && actressModel.currentProfile.profile_image_url ?
                                         actressModel.currentProfile.profile_image_url : ""
                        galleryImages: actressModel && actressModel.currentProfile.gallery_images ?
                                       actressModel.currentProfile.gallery_images : []
                        onAddProfileImageRequested: profileFileDialog.open()
                        onAddGalleryImageRequested: galleryFileDialog.open()
                        onProfileImagesDropped: function(urls) {
                            root._uploadPaths(root._localPaths(urls), true)
                        }
                        onGalleryImagesDropped: function(urls) {
                            root._uploadPaths(root._localPaths(urls), false)
                        }
                    }
                }

                // 이름 블록
                Rectangle {
                    width: parent.width - Theme.spacingMd * 2
                    x: Theme.spacingMd
                    implicitHeight: nameSection.implicitHeight + Theme.spacingMd * 2
                    color: Theme.surface
                    border.color: Theme.glassBorder
                    radius: Theme.radiusMd

                    ColumnLayout {
                        id: nameSection
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm

                        Text {
                            visible: !root.isEditMode
                            text: (actressModel && actressModel.currentProfile.name_ko) || "-"
                            font.pixelSize: 34
                            font.bold: true
                            color: Theme.textPrimary
                            Layout.fillWidth: true
                        }
                        TextField {
                            id: editNameKo
                            visible: root.isEditMode
                            Layout.fillWidth: true
                            placeholderText: "한글 이름"
                            color: Theme.textPrimary
                            background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.accentNeon }
                        }

                        GridLayout {
                            columns: 2
                            columnSpacing: 16
                            rowSpacing: 8
                            Layout.fillWidth: true

                            Text { text: "로마자"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                            Text {
                                visible: !root.isEditMode
                                text: (actressModel && actressModel.currentProfile.romaji) || "-"
                                color: Theme.textPrimary
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }
                            TextField {
                                id: editRomaji
                                visible: root.isEditMode
                                Layout.fillWidth: true
                                color: Theme.textPrimary
                                background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder }
                            }

                            Text { text: "일본어"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                            Text {
                                visible: !root.isEditMode
                                text: (actressModel && actressModel.currentProfile.name_ja) || "-"
                                color: Theme.textPrimary
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }
                            TextField {
                                id: editNameJa
                                visible: root.isEditMode
                                Layout.fillWidth: true
                                color: Theme.textPrimary
                                background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder }
                            }
                        }
                    }
                }

                // 스펙
                Rectangle {
                    width: parent.width - Theme.spacingMd * 2
                    x: Theme.spacingMd
                    implicitHeight: specSection.implicitHeight + Theme.spacingMd * 2
                    color: Theme.surface
                    border.color: Theme.glassBorder
                    radius: Theme.radiusMd

                    GridLayout {
                        id: specSection
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingMd
                        columns: 4
                        columnSpacing: 16
                        rowSpacing: 10

                        Text { text: "생년월일"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                        RowLayout {
                            visible: !root.isEditMode
                            spacing: 10
                            Text {
                                text: {
                                    var bd = actressModel && actressModel.currentProfile.birth_date
                                    if (!bd) return "-"
                                    return String(bd).length >= 10 ? String(bd).substring(0, 10) : String(bd)
                                }
                                color: Theme.textPrimary
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                            }
                            Text {
                                visible: root.formatAgeLabel(actressModel && actressModel.currentProfile.birth_date).length > 0
                                text: root.formatAgeLabel(actressModel && actressModel.currentProfile.birth_date)
                                color: Theme.textSecondary
                                font.pixelSize: 14
                                font.weight: Font.Medium
                            }
                        }
                        RowLayout {
                            visible: root.isEditMode
                            spacing: 10
                            TextField {
                                id: editBirthDate
                                Layout.fillWidth: true
                                Layout.preferredWidth: 120
                                placeholderText: "YYYY-MM-DD"
                                color: Theme.textPrimary
                                background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder }
                            }
                            Text {
                                visible: root.formatAgeLabel(editBirthDate.text).length > 0
                                text: root.formatAgeLabel(editBirthDate.text)
                                color: Theme.textSecondary
                                font.pixelSize: 14
                                font.weight: Font.Medium
                            }
                        }
                        Text { text: "키"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                        Text {
                            visible: !root.isEditMode
                            text: {
                                var h = actressModel && actressModel.currentProfile.height
                                return h ? h + " cm" : "-"
                            }
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        TextField {
                            id: editHeight
                            visible: root.isEditMode
                            placeholderText: "cm"
                            inputMethodHints: Qt.ImhDigitsOnly
                            color: Theme.textPrimary
                            background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder }
                        }

                        Text { text: "B-W-H"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                        Text {
                            visible: !root.isEditMode
                            text: {
                                var p = actressModel && actressModel.currentProfile
                                if (!p) return "-"
                                return (p.bust || "-") + "-" + (p.waist || "-") + "-" + (p.hip || "-") + " cm"
                            }
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                            Layout.columnSpan: 3
                        }
                        RowLayout {
                            visible: root.isEditMode
                            Layout.columnSpan: 3
                            TextField { id: editBust; placeholderText: "B"; implicitWidth: 50; color: Theme.textPrimary
                                background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder } }
                            TextField { id: editWaist; placeholderText: "W"; implicitWidth: 50; color: Theme.textPrimary
                                background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder } }
                            TextField { id: editHip; placeholderText: "H"; implicitWidth: 50; color: Theme.textPrimary
                                background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder } }
                        }

                        Text { text: "컵사이즈"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                        Text {
                            visible: !root.isEditMode
                            Layout.columnSpan: 3
                            text: root.formatCupSize(actressModel && actressModel.currentProfile.cup_size)
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        RowLayout {
                            visible: root.isEditMode
                            Layout.columnSpan: 3
                            Layout.fillWidth: true
                            spacing: 10

                            TextField {
                                id: editCupSize
                                Layout.preferredWidth: 56
                                maximumLength: 1
                                placeholderText: "E"
                                color: Theme.textPrimary
                                inputMethodHints: Qt.ImhUppercaseOnly
                                background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder }
                                onTextChanged: {
                                    var n = root.normalizeCupSize(text)
                                    if (text !== n) {
                                        var pos = cursorPosition
                                        text = n
                                        cursorPosition = Math.min(pos, text.length)
                                    }
                                }
                            }

                            Text {
                                visible: root.formatCupSize(editCupSize.text) !== "-"
                                text: root.formatCupSize(editCupSize.text)
                                color: Theme.textSecondary
                                font.pixelSize: 14
                                font.weight: Font.Medium
                            }
                        }

                        Text { text: "데뷔"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                        Text {
                            visible: !root.isEditMode
                            text: root.formatDebut(actressModel && actressModel.currentProfile.debut_date)
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        TextField {
                            id: editDebutDate
                            visible: root.isEditMode
                            placeholderText: "YYYY-MM-DD"
                            color: Theme.textPrimary
                            background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder }
                        }
                        Text { text: "소속사"; color: Theme.textSecondary; font.pixelSize: 14; font.weight: Font.Medium }
                        Text {
                            visible: !root.isEditMode
                            text: (actressModel && actressModel.currentProfile.agency) || "-"
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        TextField {
                            id: editAgency
                            visible: root.isEditMode
                            Layout.columnSpan: 3
                            Layout.fillWidth: true
                            color: Theme.textPrimary
                            background: Rectangle { color: Theme.surfaceLight; radius: 4; border.color: Theme.glassBorder }
                        }
                    }
                }

                // 즐겨찾기
                Rectangle {
                    width: parent.width - Theme.spacingMd * 2
                    x: Theme.spacingMd
                    implicitHeight: favSection.implicitHeight + Theme.spacingMd * 2
                    color: Theme.surface
                    border.color: Theme.glassBorder
                    radius: Theme.radiusMd

                    RowLayout {
                        id: favSection
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingLg

                        Column {
                            spacing: 6
                            Text {
                                text: "즐겨찾기"
                                color: favoriteSwitch.checked ? "#FFFFFF" : Theme.textSecondary
                                font.pixelSize: 15
                                font.bold: favoriteSwitch.checked
                            }
                            Switch {
                                id: favoriteSwitch
                                checked: (actressModel && actressModel.currentProfile.is_favorite) || false
                                onClicked: {
                                    if (actressModel && actressModel.currentProfile.id)
                                        actressModel.updateProfile(actressModel.currentProfile.id,
                                            { "is_favorite": checked })
                                }

                                indicator: Rectangle {
                                    implicitWidth: 46
                                    implicitHeight: 24
                                    x: favoriteSwitch.leftPadding
                                    y: parent.height / 2 - height / 2
                                    radius: 12
                                    color: favoriteSwitch.checked ? "#FFFFFF" : Theme.surfaceLight
                                    border.color: favoriteSwitch.checked ? "#FFFFFF" : Theme.glassBorder
                                    border.width: 1

                                    Rectangle {
                                        x: favoriteSwitch.checked ? parent.width - width - 3 : 3
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 18
                                        height: 18
                                        radius: 9
                                        color: favoriteSwitch.checked ? Theme.accentNeon : Theme.textMuted
                                        Behavior on x { NumberAnimation { duration: Theme.animFast } }
                                    }
                                }
                            }
                        }

                        Column {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                text: "관심도 " + intensitySlider.value.toFixed(1)
                                color: intensitySlider.value > 0 ? "#FFFFFF" : Theme.textSecondary
                                font.pixelSize: 15
                                font.bold: intensitySlider.value > 0
                            }
                            Slider {
                                id: intensitySlider
                                width: Math.min(280, parent.width)
                                from: 0; to: 10; stepSize: 0.5
                                value: (actressModel && actressModel.currentProfile.favorite_intensity) || 5.0
                                onMoved: intensityTimer.restart()

                                background: Rectangle {
                                    x: intensitySlider.leftPadding
                                    y: intensitySlider.topPadding + intensitySlider.availableHeight / 2 - height / 2
                                    implicitWidth: 200
                                    implicitHeight: 6
                                    width: intensitySlider.availableWidth
                                    height: implicitHeight
                                    radius: 3
                                    color: Theme.surfaceLight

                                    Rectangle {
                                        width: intensitySlider.visualPosition * parent.width
                                        height: parent.height
                                        radius: 3
                                        color: intensitySlider.value > 0 ? "#FFFFFF" : Theme.glassBorder
                                    }
                                }

                                handle: Rectangle {
                                    x: intensitySlider.leftPadding + intensitySlider.visualPosition
                                            * (intensitySlider.availableWidth - width)
                                    y: intensitySlider.topPadding + intensitySlider.availableHeight / 2 - height / 2
                                    implicitWidth: 20
                                    implicitHeight: 20
                                    width: implicitWidth
                                    height: implicitHeight
                                    radius: 10
                                    color: "#FFFFFF"
                                    border.color: intensitySlider.value > 0 ? Theme.accentNeon : Theme.glassBorder
                                    border.width: 2
                                }
                            }
                        }
                    }
                }

                // 프로필 소개
                Rectangle {
                    width: parent.width - Theme.spacingMd * 2
                    x: Theme.spacingMd
                    implicitHeight: profileIntroSection.implicitHeight + Theme.spacingMd * 2
                    color: Theme.surface
                    border.color: Theme.glassBorder
                    radius: Theme.radiusMd

                    ColumnLayout {
                        id: profileIntroSection
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm

                        Text {
                            text: "프로필 소개"
                            color: Theme.textSecondary
                            font.pixelSize: 14
                            font.weight: Font.Medium
                        }
                        TextArea {
                            id: profileTextArea
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.max(72, contentHeight + padding * 2)
                            wrapMode: TextEdit.Wrap
                            placeholderText: "AVDBS 등에서 가져온 소개..."
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.Normal
                            selectByMouse: true
                            padding: 8
                            onTextChanged: { if (!root._suppressSave) profileTextTimer.restart() }

                            background: Rectangle {
                                color: Theme.surfaceLight
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                            }
                        }
                    }
                }

                // 출연 작품 장르
                Rectangle {
                    width: parent.width - Theme.spacingMd * 2
                    x: Theme.spacingMd
                    implicitHeight: genreSection.implicitHeight + Theme.spacingMd * 2
                    color: Theme.surface
                    border.color: Theme.glassBorder
                    radius: Theme.radiusMd

                    Column {
                        id: genreSection
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm

                        Text {
                            text: "출연 작품 장르 (" + workGenresModel.count + ")"
                            color: Theme.textSecondary
                            font.pixelSize: 12
                        }

                        Flow {
                            width: parent.width
                            spacing: 8
                            Repeater {
                                model: workGenresModel
                                delegate: Rectangle {
                                    readonly property bool selected: root.selectedGenreFilter === model.name
                                    width: chipText.width + 16
                                    height: 28
                                    radius: 14
                                    color: selected
                                        ? Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.18)
                                        : Theme.surfaceLight
                                    border.color: selected ? Theme.accentNeon : Theme.glassBorder
                                    Text {
                                        id: chipText
                                        anchors.centerIn: parent
                                        text: model.name
                                        color: selected ? "#FFFFFF" : Theme.accentNeon
                                        font.pixelSize: 13
                                        font.bold: selected
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.setGenreFilter(model.name)
                                    }
                                }
                            }
                        }

                        Text {
                            visible: workGenresModel.count === 0
                            text: "라이브러리 작품에서 집계된 장르가 없습니다."
                            color: Theme.textMuted
                            font.pixelSize: 12
                        }
                    }
                }

                // 출연 작품 카드
                Rectangle {
                    width: parent.width - Theme.spacingMd * 2
                    x: Theme.spacingMd
                    implicitHeight: worksSection.implicitHeight + Theme.spacingMd * 2
                    color: Theme.surface
                    border.color: Theme.glassBorder
                    radius: Theme.radiusMd

                    Column {
                        id: worksSection
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingSm

                        RowLayout {
                            width: parent.width
                            spacing: Theme.spacingSm

                            Text {
                                Layout.fillWidth: true
                                text: {
                                    var n = worksListModel.count
                                    var total = root._allWorks.length
                                    if (root.selectedGenreFilter && n !== total)
                                        return "출연 작품 (" + n + " / " + total + ")"
                                    return "출연 작품 (" + n + ")"
                                }
                                color: Theme.textSecondary
                                font.pixelSize: 12
                            }

                            Flow {
                                Layout.alignment: Qt.AlignRight
                                spacing: 6
                                Repeater {
                                    model: root._worksSortOptions
                                    delegate: Rectangle {
                                        readonly property bool active: root.worksSortKey === modelData.key
                                        width: sortChipText.width + 16
                                        height: 26
                                        radius: 13
                                        color: active
                                            ? Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.18)
                                            : Theme.surfaceLight
                                        border.color: active ? Theme.accentNeon : Theme.glassBorder
                                        Text {
                                            id: sortChipText
                                            anchors.centerIn: parent
                                            text: modelData.label + (active
                                                ? (root.worksSortAscending ? " ↑" : " ↓")
                                                : "")
                                            color: active ? "#FFFFFF" : Theme.textSecondary
                                            font.pixelSize: 12
                                            font.bold: active
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.toggleWorksSort(modelData.key)
                                        }
                                    }
                                }
                            }
                        }

                        Item {
                            id: worksGridHost
                            width: parent.width
                            height: worksGrid.height

                            readonly property int cardCellW: 210
                            readonly property int cardCellH: 310
                            readonly property int gridColumns: Math.max(1, Math.floor(width / cardCellW))
                            readonly property real gridWidth: gridColumns * cardCellW

                            GridView {
                                id: worksGrid
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: worksGridHost.gridWidth
                                height: contentHeight
                                clip: true
                                interactive: false
                                cellWidth: worksGridHost.cardCellW
                                cellHeight: worksGridHost.cardCellH
                                model: worksListModel
                                delegate: PosterCard {
                                    width: worksGrid.cellWidth - 8
                                    height: worksGrid.cellHeight - 8
                                    productCode: model.product_code || ""
                                    titleKo: model.title_ko || model.titleKo || ""
                                    actorsKo: model.actors_ko || model.actorsKo || ""
                                    coverPath: model.cover_path || model.coverPath || ""
                                    favoriteScore: model.favorite_score || 0
                                    onClicked: function(pc) {
                                        if (!pc) return
                                        var aid = (actressModel && actressModel.currentProfile.id)
                                            ? actressModel.currentProfile.id : 0
                                        window.navigateToLibraryDetail(pc, aid)
                                    }
                                }
                            }
                        }

                        Text {
                            visible: worksListModel.count === 0 && root._allWorks.length === 0
                            text: "라이브러리에 등록된 작품이 없습니다."
                            color: Theme.textMuted
                            font.pixelSize: 13
                        }
                        Text {
                            visible: worksListModel.count === 0 && root._allWorks.length > 0 && root.selectedGenreFilter
                            text: "선택한 장르에 해당하는 작품이 없습니다."
                            color: Theme.textMuted
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }
    }

    // 갤러리 클릭 — 상세 패널 전체 오버레이 (크게 보기)
    Rectangle {
        id: galleryPreviewOverlay
        anchors.fill: parent
        visible: actressGallery.previewOverlayUrl !== ""
        color: Qt.rgba(0, 0, 0, 0.88)
        z: 200
        focus: visible
        Keys.onEscapePressed: actressGallery.previewOverlayUrl = ""

        MouseArea {
            anchors.fill: parent
            onClicked: actressGallery.previewOverlayUrl = ""
        }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(galleryPreviewOverlay.width * 0.90, 760)
            height: Math.min(galleryPreviewOverlay.height * 0.86, 920)
            radius: Theme.radiusMd
            color: Theme.bgSecondary
            border.color: Theme.accentNeon
            border.width: 1
            clip: true

            Image {
                anchors.fill: parent
                anchors.margins: 10
                source: actressGallery.previewOverlayUrl
                       ? Theme.pathToUrl(actressGallery.previewOverlayUrl) : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }

            MouseArea {
                anchors.fill: parent
                onClicked: function(mouse) { mouse.accepted = true }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.spacingMd
            text: "바깥 영역 클릭 또는 ESC로 닫기"
            color: Theme.textMuted
            font.pixelSize: 12
        }
    }
}
