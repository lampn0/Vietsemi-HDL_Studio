# Qt 6 / PySide6 trong Vietsemi HDL Studio

Tài liệu ôn lại Qt 6 (PySide6) theo đúng những gì repo này dùng: các khái niệm nền, các component
theo nhóm kèm hàm và signal hay dùng, rồi các mẫu code riêng của repo. Mỗi mục trỏ tới một chỗ
dùng thật trong `src/gui/` để đọc tiếp. Danh sách lớp lấy từ các câu `import` của `src/` và `bin/`
(PySide6 6.10).

Đọc cùng [architecture.md](architecture.md) (code tổ chức thế nào) và
[development.md](development.md) (quy ước). Tài liệu chính thức: *Qt for Python*
(doc.qt.io/qtforpython-6), mục *Widgets* và *Graphics View Framework*.

---

## 1. Bức tranh tổng

```
QApplication                      bin/hdlstudio.py: app = QApplication(sys.argv) ... app.exec()
└── QMainWindow                   DesignManager, MainWindow (FSM), BdEditorWindow, TextEditorWindow
    ├── menuBar()  -> QMenu -> QAction
    ├── QToolBar   -> QAction / QToolButton
    ├── centralWidget()           QTabWidget / QSplitter / QGraphicsView / CodeEditor
    ├── QDockWidget               panel dock được (Diagram Browser, Messages, Properties)
    └── statusBar()
QDialog                           các hộp thoại, mở bằng dlg.exec()
```

PySide6 chia thành 3 module chính:

| Module | Chứa | Lớp repo dùng nhiều nhất |
|---|---|---|
| `QtCore` | không có giao diện: đối tượng, signal, timer, hình học, cài đặt | `Qt` (enum), `QPointF`, `QRectF`, `Signal`, `QTimer`, `QSettings`, `QEvent` |
| `QtGui` | vẽ và tài nguyên đồ họa, action | `QPainter`, `QPen`, `QColor`, `QFont`, `QPolygonF`, `QPainterPath`, `QAction`, `QKeySequence`, `QIcon` |
| `QtWidgets` | các widget | layout, ô nhập liệu, cây/bảng, `QMainWindow`, `QDialog`, Graphics View |

`QAction` nằm trong `QtGui` từ Qt 6 (Qt 5 để trong `QtWidgets`): một lỗi import hay gặp khi
đọc ví dụ cũ trên mạng.

---

## 2. Năm khái niệm nền

### 2.1 Cây cha-con (parent) và quản lý bộ nhớ
Mọi `QObject` có thể có cha. Khi cha bị hủy, con bị hủy theo. Widget con được vẽ bên trong cha.
Vì vậy code luôn truyền `parent` (`QTimer(self)`, `QAction(text, self)`, `super().__init__(parent)`)
và không phải tự giải phóng. Một widget không có cha và được `show()` là một cửa sổ riêng.

### 2.2 Signal và slot
Một đối tượng phát (`emit`) signal; các hàm đã `connect` vào signal đó được gọi.

```python
button.clicked.connect(self.add_row)                 # signal có sẵn của Qt
self.kind.currentIndexChanged.connect(self._kind_changed)
b.clicked.connect(lambda: edit.setText(...))         # slot là lambda

class FsmScene(QGraphicsScene):
    changed_model = Signal()                         # signal tự định nghĩa: khai báo ở mức class
    text_edit_requested = Signal(object, str)        # kèm kiểu tham số
...
self.fsm_scene.changed_model.emit()                  # phát
self.scene.changed_model.connect(self.model_changed) # nhận (main_window.py)
```

Bẫy hay gặp: lambda trong vòng lặp phải "chốt" biến bằng tham số mặc định,
`lambda checked=False, w=widget: self.tabs.setCurrentWidget(w)` (xem `main_window.py`).
`triggered` / `clicked` truyền thêm tham số `checked`, nên lambda cần nhận nó.

### 2.3 Sự kiện (event): override `xxxEvent`
Chuột, phím, vẽ, đổi kích thước... đến widget qua các hàm ảo. Muốn đổi hành vi thì viết đè hàm
đó trong lớp con, và gọi `super()` cho những trường hợp không xử lý:

| Hàm | Khi nào | Ví dụ trong repo |
|---|---|---|
| `paintEvent(e)` | widget cần vẽ lại | `_LineArea.paintEvent` ([text_editor.py](../src/gui/text_editor.py)) |
| `resizeEvent(e)` | đổi kích thước | `CodeEditor.resizeEvent` đặt lại cột số dòng |
| `keyPressEvent(e)` | nhấn phím | `CodeEditor.keyPressEvent`: Tab thành dấu cách |
| `mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent` / `mouseDoubleClickEvent` | chuột | `FsmScene`, `StateItem` ([diagram.py](../src/gui/diagram.py)) |
| `wheelEvent(e)` | con lăn | `FsmGraphicsView.wheelEvent`: Ctrl+lăn để zoom |
| `contextMenuEvent(e)` | chuột phải | `FsmScene.contextMenuEvent`: popup menu kiểu tool cũ |
| `closeEvent(e)` | đóng cửa sổ | hỏi Save / Discard / Cancel (`e.ignore()` để không đóng) |
| `dragEnterEvent` / `dropEvent` | kéo thả | `bd_editor.py`: thả component từ Component Browser |

Muốn chặn sự kiện của một widget khác mà không viết lớp con thì dùng `eventFilter`
(`installEventFilter`), repo dùng ở `main_window.py` và `design_manager.py`.

### 2.4 Layout
Không đặt tọa độ tay cho widget; đưa chúng vào layout:

| Layout | Dùng khi | Hàm chính |
|---|---|---|
| `QVBoxLayout` / `QHBoxLayout` | xếp dọc / ngang | `addWidget(w, stretch)`, `addLayout(l)`, `addStretch(1)`, `setContentsMargins(0,0,0,0)` |
| `QFormLayout` | form "nhãn: ô nhập" | `addRow('Nhãn', widget)`, `addRow(widget)` |
| `QGridLayout` | lưới hàng/cột | `addWidget(w, row, col, rowSpan, colSpan)` |

`QVBoxLayout(self)` vừa tạo vừa gán layout cho widget `self`.

### 2.5 Enum `Qt`
Hằng số nằm trong `Qt`: `Qt.AlignRight`, `Qt.LeftButton`, `Qt.ControlModifier`, `Qt.Key_Tab`,
`Qt.RightDockWidgetArea`, `Qt.KeepAspectRatio`... PySide6 chấp nhận cả dạng ngắn này lẫn dạng đầy
đủ `Qt.AlignmentFlag.AlignRight`; repo dùng dạng ngắn. Cờ kết hợp bằng `|`, kiểm tra bằng `&`
(`if mods & Qt.ControlModifier:`).

---

## 3. Component theo nhóm

Cột "Ở đâu" là file trong `src/gui/` dùng lớp đó nhiều nhất.

### 3.1 Ứng dụng và cửa sổ

| Lớp | Để làm gì | Hàm / thuộc tính hay dùng | Signal | Ở đâu |
|---|---|---|---|---|
| `QApplication` | một đối tượng cho cả chương trình, chạy vòng lặp sự kiện | `exec()`, `QApplication.clipboard()`, `QApplication.instance()` | | `bin/hdlstudio.py` |
| `QMainWindow` | cửa sổ chính có menu, toolbar, dock, status bar | `setCentralWidget`, `menuBar()`, `addToolBar`, `addDockWidget(area, dock)`, `resizeDocks`, `statusBar().showMessage(msg, ms)`, `setWindowTitle`, `saveGeometry`/`restoreGeometry` (vị trí cửa sổ trong session) | | `main_window.py`, `bd_editor.py`, `design_manager.py` |
| `QDialog` | hộp thoại | `exec()` (trả `Accepted`/`Rejected`), `accept()`, `reject()`, `setWindowTitle`, `setMinimumWidth` | `accepted`, `rejected`, `finished` | `dialogs.py`, `bd_dialogs.py`, `sm_*_dialog.py` |
| `QWidget` | lớp gốc mọi widget, hoặc khung chứa trống | `show/hide`, `setEnabled`, `setVisible`, `setToolTip`, `setFont`, `setStyleSheet`, `setFixedSize`, `sizeHint` (override), `update()` (yêu cầu vẽ lại) | | khắp nơi |
| `QDockWidget` | panel gắn được vào mép cửa sổ | `setWidget`, `setObjectName`, `hide/show` | `visibilityChanged` | `main_window.py`: Diagram Browser, Messages |

### 3.2 Ô nhập liệu và nút

| Lớp | Để làm gì | Hàm hay dùng | Signal | Ở đâu |
|---|---|---|---|---|
| `QLabel` | chữ (hỗ trợ HTML rút gọn) | `setText`, `setStyleSheet('color: #c00000')`, `setWordWrap` | `linkActivated` | `dialogs.py`: dòng báo lỗi đỏ |
| `QLineEdit` | ô nhập một dòng | `text()`, `setText`, `setPlaceholderText`, `setReadOnly`, `selectAll` | `textChanged`, `editingFinished`, `returnPressed` | `dialogs.py`, `bd_editor.py` (sửa tên net tại chỗ) |
| `QPlainTextEdit` | ô nhập nhiều dòng, không định dạng | `toPlainText()`, `setPlainText`, `setPlaceholderText`, `setMaximumHeight` | `textChanged` | `props.py`, `dialogs.py` (danh sách port) |
| `QComboBox` | danh sách chọn | `addItem(text, data)`, `addItems`, `currentText()`, `currentData()`, `setCurrentIndex`, `setCurrentText`, `setEditable` | `currentIndexChanged`, `currentTextChanged` | `dialogs.py`: chọn library, loại, ngôn ngữ |
| `QCheckBox` | ô tick | `isChecked()`, `setChecked` | `toggled(bool)`, `stateChanged` | `main_settings.py`, `dm_options.py` |
| `QRadioButton` + `QButtonGroup` | chọn một trong nhiều | `addButton(b)`, `checkedButton()`, `buttons()` | `buttonClicked` | `sm_machine_dialog.py`: Sequential / 1-Hot / Gray... |
| `QSpinBox` | số nguyên | `setRange`, `value()`, `setValue` | `valueChanged(int)` | `props.py`: priority |
| `QPushButton` | nút bấm | `setDefault`, `setEnabled` | `clicked` | khắp nơi |
| `QToolButton` | nút trên toolbar, có thể kèm menu thả xuống | `setDefaultAction`, `setMenu`, `setPopupMode` | `triggered(QAction)` | `toolbars.py`: nút nhiều lựa chọn |
| `QDialogButtonBox` | hàng nút chuẩn OK / Cancel / Apply | `QDialogButtonBox(QDialogButtonBox.Ok \| QDialogButtonBox.Cancel)`, `button(...)` | `accepted`, `rejected`, `clicked` | `dialogs.py` `_Base` |

### 3.3 Khung chứa

| Lớp | Để làm gì | Hàm hay dùng | Signal | Ở đâu |
|---|---|---|---|---|
| `QGroupBox` | khung có tiêu đề bao một nhóm ô | `QGroupBox('Tiêu đề')`, gán layout, `setCheckable` | `toggled` | `main_settings.py`, `sm_machine_dialog.py` |
| `QTabWidget` | các tab | `addTab(w, 'Tên')`, `setCurrentWidget`, `currentIndex`, `setTabsClosable` | `currentChanged`, `tabCloseRequested` | `design_manager.py`: tab Project + tab library; `main_window.py`: Diagram / Signals / Parameters |
| `QStackedWidget` | nhiều trang, hiện một trang (dialog có cây trang bên trái) | `addWidget`, `setCurrentIndex`, `setCurrentWidget` | `currentChanged` | `sm_machine_dialog.py`, `props.py` |
| `QSplitter` | chia vùng kéo được | `addWidget`, `setSizes([300, 250])`, `setOrientation` | `splitterMoved` | `main_window.py`: Structure Navigator / Content |
| `QFrame` | đường kẻ, khung viền | `setFrameShape(QFrame.HLine)` | | `dm_options.py` |

### 3.4 Danh sách, cây và bảng
Repo dùng các lớp **"Widget"** (dữ liệu nằm ngay trong item), không dùng mô hình Model/View đầy đủ
(`QAbstractItemModel` + `QTreeView`). Đơn giản hơn, đủ cho kích thước dữ liệu ở đây.

| Lớp | Để làm gì | Hàm hay dùng | Signal | Ở đâu |
|---|---|---|---|---|
| `QListWidget` / `QListWidgetItem` | danh sách | `addItem`, `clear`, `currentRow`, `item(i)`, `item.setData(Qt.UserRole, obj)`, `item.data(Qt.UserRole)`, `scrollToBottom` | `itemDoubleClicked`, `currentRowChanged` | `main_window.py`: cửa sổ Messages; `text_editor.py`: danh sách lỗi |
| `QTreeWidget` / `QTreeWidgetItem` | cây nhiều cột | `setHeaderLabels`, `addTopLevelItem`, `QTreeWidgetItem(parent, ['cột1', 'cột2'])`, `item.setText(col, s)`, `setIcon`, `setForeground(col, QBrush)`, `setExpanded`, `setData(0, Qt.UserRole, obj)` | `itemDoubleClicked`, `itemExpanded`, `currentItemChanged`, `itemSelectionChanged` | `design_manager.py`: Design Units / Files / Hierarchy; `main_window.py`: Structure Navigator |
| `QTableWidget` / `QTableWidgetItem` | bảng | `setRowCount`, `setColumnCount`, `setHorizontalHeaderLabels`, `setItem(r, c, item)`, `item(r, c).text()`, `insertRow`, `removeRow`, `selectedItems`, `setItemDelegateForColumn` | `itemChanged`, `cellDoubleClicked` | [tables.py](../src/gui/tables.py): Signals / Parameters Table |
| `QHeaderView` | tiêu đề cột/hàng của bảng/cây | `setSectionResizeMode(QHeaderView.Interactive)`, `setStretchLastSection`, `setDefaultSectionSize` | `sectionClicked` | `tables.py` |
| `QStyledItemDelegate` | ô có editor riêng (ví dụ combo trong ô bảng) | override `createEditor`, `setEditorData`, `setModelData` | | `tables.py` `ComboDelegate` |

Mẹo: khi tự điền dữ liệu vào bảng, `itemChanged` cũng bắn ra. Repo dùng cờ `self._loading = True`
(hoặc `blockSignals(True)`) để bỏ qua những lần đó.

### 3.5 Hộp thoại có sẵn
Gọi một dòng, không cần tự tạo lớp:

| Gọi | Trả về | Ở đâu |
|---|---|---|
| `QMessageBox.information / warning / critical(parent, tiêu đề, nội dung)` | | `context.py` |
| `QMessageBox.question(parent, t, s, buttons)` | nút được bấm (so với `QMessageBox.Yes`...) | hỏi trước khi ghi đè file |
| `QFileDialog.getOpenFileName(parent, t, dir, 'Project files (*.hdp)')` | `(path, filter)`, path rỗng nếu Cancel | `design_manager.py` |
| `QFileDialog.getExistingDirectory(parent, t, dir)` | thư mục hoặc `''` | `dialogs.py` `_dir_row` |
| `QInputDialog.getText(parent, t, nhãn, text=...)` | `(text, ok)` | `main_window.py`, `bd_editor.py` (đổi tên) |
| `QColorDialog.getColor(initial, parent)` | `QColor` (`isValid()` sai nếu Cancel) | `bd_dialogs.py` Appearance |

### 3.6 Lệnh: action, menu, toolbar, phím tắt

| Lớp | Để làm gì | Hàm hay dùng | Signal |
|---|---|---|---|
| `QAction` | một lệnh: chữ, icon, phím tắt, bật/tắt; dùng chung cho menu và toolbar | `QAction(text, parent)`, `setShortcut(s)`, `setIcon`, `setToolTip`, `setStatusTip`, `setCheckable`, `setChecked`, `setEnabled`, `setData` | `triggered(checked)`, `toggled` |
| `QActionGroup` | nhóm action loại trừ nhau (chọn tool) | `addAction`, `setExclusive(True)` | `triggered` |
| `QMenu` | menu, popup chuột phải | `addAction`, `addMenu`, `addSeparator`, `exec(globalPos)` | `aboutToShow` |
| `QToolBar` | thanh công cụ | `addAction`, `addWidget`, `addSeparator`, `setIconSize(QSize(...))` | |
| `QKeySequence` | phím tắt | `QKeySequence('Ctrl+Shift+G')`, `QKeySequence.Save` (chuẩn của hệ điều hành) | |

Trong repo, action không được tạo rải rác mà theo một quy trình cố định (mục 4.2).

### 3.7 Soạn thảo văn bản
`QPlainTextEdit` là lõi của editor HDL ([text_editor.py](../src/gui/text_editor.py)):

| Lớp | Vai trò | Hàm hay dùng |
|---|---|---|
| `QPlainTextEdit` | vùng soạn thảo | `document()`, `textCursor()`, `setTextCursor`, `firstVisibleBlock`, `blockBoundingGeometry`, `setViewportMargins` (chừa chỗ cột số dòng), `setExtraSelections` (tô dòng), `centerCursor`, `find` |
| `QTextDocument` / block | nội dung, mỗi dòng là một block | `findBlockByLineNumber`, `block.blockNumber()`, `block.next()` |
| `QTextCursor` | vị trí / vùng chọn | `QTextCursor(block)`, `positionInBlock()`, `hasSelection()`, `movePosition` |
| `QSyntaxHighlighter` | tô màu cú pháp | override `highlightBlock(text)`, gọi `setFormat(start, len, fmt)` ([code_view.py](../src/gui/code_view.py)) |
| `QTextCharFormat` | định dạng chữ | `setForeground`, `setFontWeight` |

Signal của `QPlainTextEdit` repo dùng: `blockCountChanged`, `updateRequest(rect, dy)` (cuộn cột
số dòng theo text), `cursorPositionChanged`, `textChanged`, `modificationChanged`.

### 3.8 Graphics View: nền của hai editor sơ đồ
Ba tầng, mỗi tầng một việc:

| Lớp | Vai trò | Hàm hay dùng | Ở đâu |
|---|---|---|---|
| `QGraphicsScene` | chứa mọi item, tọa độ "thế giới" (scene), quản lý chọn | `addItem`, `removeItem`, `items()`, `itemAt(pos, transform)`, `selectedItems()`, `clearSelection`, `itemsBoundingRect`, `mouseGrabberItem` | `FsmScene` ([diagram.py](../src/gui/diagram.py)), `BdScene` (`bd_editor.py`) |
| `QGraphicsView` | widget nhìn vào scene: zoom, cuộn, lưới | `scale`, `setTransform`, `transform().m11()` (mức zoom), `fitInView`, `centerOn`, `mapToScene` / `mapFromScene`, `setDragMode(RubberBandDrag)`, `setTransformationAnchor(AnchorUnderMouse)`, override `drawBackground` | `FsmGraphicsView` |
| `QGraphicsItem` | một đối tượng trên sơ đồ | **bắt buộc** override `boundingRect()` và `paint(p, opt, widget)`; `setPos`, `pos()`, `scenePos()`, `setFlags`, `setZValue`, `isSelected`, `prepareGeometryChange()` (trước khi đổi kích thước), `update()` | `NodeItem`, `StateItem`, `TransitionItem`... |
| item có sẵn | khỏi tự vẽ | `QGraphicsPathItem`, `QGraphicsEllipseItem`, `QGraphicsPolygonItem`, `QGraphicsSimpleTextItem` | `TransitionItem(QGraphicsPathItem)` |
| `QRubberBand` | khung chữ nhật khi kéo vùng | `setGeometry`, `show/hide` | View Area trong `FsmGraphicsView` |

Ba hệ tọa độ: **item** (gốc tại `pos()` của item, `paint` vẽ trong hệ này), **scene** (chung cho
cả sơ đồ; trong repo 1 đơn vị scene = 75 đơn vị trong file của tool cũ) và **view** (pixel trên màn hình). Đổi qua lại
bằng `mapToScene` / `mapFromScene` / `mapToItem`.

Cờ của item: `ItemIsMovable` (kéo được), `ItemIsSelectable`, `ItemSendsGeometryChanges` (để
`itemChange` nhận `ItemPositionChange`). `NodeItem.itemChange` dùng nó để bắt vào lưới khi kéo và
ghi vị trí mới vào model.

Signal của scene: `selectionChanged` (có sẵn) cùng các signal tự định nghĩa ở mục 4.3.

### 3.9 Vẽ: QPainter và hình học

| Lớp | Để làm gì | Hàm hay dùng |
|---|---|---|
| `QPainter` | bút vẽ, nhận trong `paint()` / `paintEvent` | `setPen`, `setBrush`, `setFont`, `setRenderHint(QPainter.Antialiasing)`, `drawEllipse`, `drawRect`, `drawLine`, `drawPolygon`, `drawPath`, `drawText(rect, flags, text)`, `drawPoints`, `fillRect`, `save()` / `restore()`, `translate`, `rotate` |
| `QPen` | nét: màu, độ dày, kiểu | `QPen(QColor(0,128,192), 2)`, `setStyle(Qt.DashLine)`, `setCosmetic(True)` (độ dày không đổi khi zoom); độ dày 0 = 1 pixel |
| `QBrush` | tô nền | `QBrush(QColor(...))`, `Qt.NoBrush` |
| `QColor` | màu | `QColor(r, g, b)`, `QColor('#c00000')`, `lighter()`, `darker()` |
| `QFont` / `QFontMetricsF` | chữ và đo chữ | `QFont('Arial', 10)`, `setBold`, `setPointSizeF`; `horizontalAdvance(text)`, `height()` (dùng để tính kích thước ô chữ) |
| `QPointF`, `QRectF`, `QLineF`, `QPolygonF` | hình học số thực | `QRectF(x, y, w, h)`, `contains`, `adjusted`, `united`, `center()`; `QLineF.angle()`, `pointAt(t)` |
| `QPainterPath` | đường cong / hình phức tạp | `moveTo`, `lineTo`, `cubicTo`, `addEllipse`; `QPainterPathStroker` tạo vùng bấm quanh một đường mảnh |
| `QTransform` | xoay / co giãn | `rotate`, `map` |
| `QIcon` / `QPixmap` | icon cho action, cây | repo vẽ icon bằng QPainter vào `QPixmap` ([icons.py](../src/gui/icons.py), `dm_icons.py`, `editor_icons.py`; ảnh xám cho trạng thái disabled qua `QIcon.addPixmap(..., QIcon.Disabled)`) |

### 3.10 Tiện ích

| Lớp | Để làm gì | Ở đâu |
|---|---|---|
| `QTimer` | hẹn giờ | `QTimer.singleShot(0, fn)` (chạy sau khi vòng lặp sự kiện rảnh, ví dụ sau khi cửa sổ đã hiện); timer `setSingleShot(True)` + `setInterval(250)` + `timeout.connect` để gộp nhiều thay đổi liên tiếp thành một lần xử lý (`main_window.py` `regen_timer`, `undo.py`) |
| `QSettings` | lưu cài đặt nhỏ của Qt (zoom, vị trí cuộn) | `undo.py` `save_view_state` / `load_view_state`; còn preference của tool lưu bằng JSON (`prefs.py`) |
| `QMimeData` + `QDrag` | kéo thả | `component_browser.py` bắt đầu kéo; `bd_editor.py` `dragEnterEvent` / `dropEvent` nhận |
| `QEvent` | kiểm tra loại sự kiện trong `eventFilter` | `main_window.py` |
| `QSize`, `QByteArray` | kích thước; dữ liệu nhị phân của `saveGeometry` (lưu dạng base64 trong session) | `toolbars.py`, `design_manager.py` |

---

## 4. Các mẫu riêng của repo

### 4.1 Dialog có kiểm tra dữ liệu: `_Base`
[dialogs.py](../src/gui/dialogs.py) `_Base(QDialog)`: `QFormLayout` + một `QLabel` đỏ báo lỗi +
OK / Cancel. OK gọi `validate()`; chỉ đóng khi `validate()` trả `''`. Dialog mới chỉ cần
kế thừa, thêm hàng bằng `self.form.addRow(...)` và viết `validate()` (xem `NewUnitDialog`).
Cách dùng từ cửa sổ gọi:

```python
dlg = NewUnitDialog(libs, current, self.prefs, self)
if dlg.exec() == QDialog.Accepted:
    ports = dlg.parsed_ports()
```

### 4.2 Lệnh theo tên của tool cũ: action -> tên -> phím -> menu
Lệnh của editor đi qua 4 chỗ (đúng như architecture.md mục 6):
1. Tạo `QAction` dưới một **key** trong `_build_actions` / `_build_menu_commands` của cửa sổ;
   hàm phụ `_act(menu, text, slot, key, icon_name)` trong `main_window.py`.
2. [command_names.py](../src/gui/command_names.py) `COMMANDS[key] = (nhãn menu, tooltip, chữ trên status bar)`, giống tool cũ.
3. [toolbars.py](../src/gui/toolbars.py): các toolbar theo thứ tự tool cũ (`FSM_TOOLBARS`, `BD_TOOLBARS`:
   Standard, ... Tools, HDL Tools, Tasks) và phím tắt (`FSM_KEYS`, `BD_KEYS`); `build_toolbars` dựng
   các toolbar từ danh sách đó, icon lấy từ [editor_icons.py](../src/gui/editor_icons.py).
4. [menus.py](../src/gui/menus.py) `arrange_menus(win, spec)`: dựng lại menu bar theo thứ tự của tool cũ.
   `'@key'` = lệnh đã có (`'@key=Nhãn'`: nhãn hiện mờ khi chưa có lệnh), `'!text'` = mục luôn mờ,
   `'-'` = vạch ngăn, `(tiêu đề, hàm)` = menu con điền lại mỗi lần mở (Open Machine, Toolbars),
   một hàm đứng riêng = phần cuối menu điền lại mỗi lần mở (danh sách cửa sổ trong Window).

### 4.3 Scene báo, cửa sổ xử lý
Item và scene **không** mở dialog hay sửa cửa sổ. Chúng phát signal của scene
(`changed_model`, `edit_requested`, `rename_requested`, `text_edit_requested`, `popup_requested`,
`message`); cửa sổ (`MainWindow`, `BdEditorWindow`) `connect` và làm phần còn lại (mở dialog, cập
nhật bảng, đánh dấu chưa lưu, sinh lại HDL). Nhờ vậy phần vẽ không phụ thuộc vào cửa sổ.

```
StateItem.mouseDoubleClickEvent ──emit──> FsmScene.rename_requested ──> MainWindow.rename_state_inline
NodeItem.mouseReleaseEvent      ──emit──> FsmScene.changed_model    ──> MainWindow.model_changed
                                                                        ├─ đánh dấu '*'
                                                                        ├─ SnapshotUndo chụp trạng thái
                                                                        └─ regen_timer -> sinh lại HDL
```

### 4.4 Undo bằng ảnh chụp: `SnapshotUndo`
[undo.py](../src/gui/undo.py): thay vì `QUndoStack` với từng lệnh, mỗi lần model đổi thì chụp cả
model thành JSON (`view.to_json()`); các thay đổi cách nhau dưới 400 ms gộp thành một bước (dùng
`QTimer`). Undo = khôi phục ảnh chụp trước. Đơn giản và khó sai, đổi lại tốn bộ nhớ hơn.

### 4.5 Model không biết Qt
Các item giữ tham chiếu tới đối tượng model (`self.obj`) và ghi thẳng vào đó
(`NodeItem.itemChange` ghi `obj.x`, `obj.y`). Model (`model.py`, `bd_model.py`) không import Qt,
nên test và script dùng được không cần giao diện.

---

## 5. Mẹo khi làm việc

* **Xem cây widget của cửa sổ đang chạy:**
  ```python
  def dump(w, depth=0):
      print('  ' * depth + type(w).__name__, w.objectName())
      for c in w.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
          dump(c, depth + 1)
  ```
* **Designer:** `pyside6-designer` có sẵn, dùng để phác thảo bố cục; repo không dùng file `.ui`
  (giao diện viết bằng code).
* **Vẽ lại không ăn:** gọi `item.update()`; nếu kích thước thay đổi thì gọi
  `prepareGeometryChange()` **trước** khi đổi, nếu không sẽ còn vệt vẽ cũ.
* **Item không bấm được ở mép:** `boundingRect()` phải bao cả phần vẽ (repo cộng thêm vài đơn vị
  cho handle chọn); vùng bấm chính xác thì override `shape()`.
* **Signal bắn lúc đang nạp dữ liệu:** `widget.blockSignals(True)` ... `False`, hoặc cờ `_loading`.
* **Lambda trong vòng lặp:** chốt biến bằng tham số mặc định (mục 2.2).
* **`exec()` chứ không phải `exec_()`:** `exec_` là tên cũ của Qt 5 / PySide2.
* **CentOS chạy không lên** ("Could not load the Qt platform plugin xcb"): cài thư viện xcb như
  [development.md](development.md) mục 1.
