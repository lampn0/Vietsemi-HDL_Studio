"""Hand-written notes of the .sm / .sb / .bd syntax reference (docs/formats/sm-sb-bd-reference.html), in
Vietnamese. format_ref.py merges them with the inventory of the sample files.

    TOPICS       sections at the top of the page: (id, title, HTML)
    TYPES        type name -> {'desc': HTML, 'keys': {key: HTML}}
    COMMON_KEYS  meaning of keys shared by many types (uid, va, xt, ...), used when a type has no
                 note of its own for that key
    CATEGORIES   (id, title) of the groups of types, in page order; CATEGORY_OF puts types in them
    CHANGES      (date, HTML) log of what was learned or changed

Mark what is not verified with UNSURE ("chưa xác minh") so it is easy to find and confirm later
(change the setting in the legacy tool, save, diff the file). Add a CHANGES line for each finding.
"""
from __future__ import annotations

TITLE = 'Cú pháp file .sm / .sb / .bd'
UNSURE = ' <span class="chip warn">chưa xác minh</span>'

# -- groups of types ------------------------------------------------------------------------
CATEGORIES = [
    ('file', 'Khung file và header'),
    ('sm', 'State machine (.sm)'),
    ('sym', 'Symbol (.sb)'),
    ('bd', 'Block diagram (.bd)'),
    ('table', 'Khai báo và bảng tín hiệu / tham số'),
    ('text', 'Text và khối text'),
    ('shape', 'Hình vẽ và thuộc tính hiển thị'),
    ('other', 'Khác'),
]

CATEGORY_OF = {
    'file': 'DocumentHdr Machine StateMachine Symbol StateDiagram VariableExpander vvPair PageSetupInfo Grid '
            'HdmGraphicsRef',
    'sm': 'ConcurrentSM SmGenChar Encoding pair State CompositeState Junction Link Transition TransitionBlock '
          'TransitionPriority SmStateActionsBlock SmResetPoint SmClockPoint SmEnablePoint SmRecoveryStatePoint '
          'InterruptPoint EntryPoint ExitPoint SmControlCondition CaseSettings',
    'sym': 'SymbolBody CptPort CptPortProtocol CPTG LogPort PortSigDisplay GenericInterface Matrix SymDeclBlock FFT',
    'bd': 'BlockDiag Wire Net WTG WWL SaComponent MWC mwParamsVisibilityOptions Instance EmbeddedInstance '
          'FrameInstance HdlText EmbeddedText PortIoIn PortIoOut PortIoInOut PortIoBuffer PortIoSlave PortIoMaster '
          'Frame FrameSequenceNumber BdJunction GenericAssociation Parameter Property Blk VhdlComponent '
          'VerilogComponent GlobalConnector Ripper Bundle Protocol PortMapFrame BdArchDeclBlock CommentGraphic',
    'table': 'LeafLogPort LogicalPort Decl LogGeneric GiElement LGroup CommonDM LogicalDM PhysicalDM Sheet SheetRow '
             'SheetCol MRCItem PVME MVa LEmptyRow RefLabelRowHdr TitleRowHdr FilterRowHdr RefLabelColHdr '
             'RowExpandColHdr GroupColHdr NameColHdr InitColHdr EolColHdr ModeColHdr TypeColHdr SignedColHdr '
             'BoundsColHdr DelayColHdr IncludeColHdr',
    'text': 'Text MLText TextAssociate BiTextGroup MlTextGroup PackageList SmLocalDecl SmProcessDecl '
            'SmSignalGenStatus CommentText RequirementText Panel',
    'shape': 'VaSet Line Rectangle Circle Triangle Spline Pentagon Diamond CompositeShape OrthoPolyLine Arc2D '
             'CustomPolygon PolyLine TripleCircle CircleInOctagon RectFrame ZoomableIcon Grouping GroupingShape '
             'Hexagon Line2D PolyLine2D',
}
_CAT = {t: c for c, names in CATEGORY_OF.items() for t in names.split()}
_ORDER = {c: i for i, (c, _) in enumerate(CATEGORIES)}


def category_of(type_name: str) -> str:
    """Group id of an object type ('other' when not listed)."""
    if type_name in _CAT:
        return _CAT[type_name]
    return 'table' if type_name.endswith(('ColHdr', 'RowHdr')) else 'other'


def category_index(type_name: str) -> int:
    """Position of the type's group on the page."""
    return _ORDER[category_of(type_name)]


# -- keys shared by many types --------------------------------------------------------------
COMMON_KEYS = {
    'uid': 'Định danh object trong file: <code>N,0</code>. Duy nhất trong file; số lớn nhất được ghi ở '
           '<code>model lastUid</code>. Object mới phải lấy uid mới (export_sm tăng <code>lastUid</code>).',
    'va': 'Thuộc tính hiển thị (<code>VaSet</code>): màu, font, nét, ẩn/hiện.',
    'xt': 'Hình chữ nhật bao (extent) <code>"x0,y0,x1,y1"</code>, đơn vị tọa độ của tool cũ. '
          'Với text, tool cũ tự tính lại khi mở file.',
    'pts': 'Danh sách điểm <code>"x,y"</code> của đường (đầu, các điểm gãy, cuối).',
    'blo': 'Gốc baseline của dòng text đầu tiên <code>"x,y"</code>.',
    'st': 'Nội dung text. Chuỗi có thể nhiều dòng (xuống dòng thật trong file). '
          'Phải đứng <b>trước</b> <code>blo</code>/<code>ju</code>/<code>tm</code>: tool cũ đọc theo thứ tự, '
          '<code>st</code> nằm sau <code>tm</code> bị hiểu sai (xem export_sm <code>_PLACE</code>).',
    'tm': 'Tên "manager" của text: cho biết vai trò của text (vd. <code>"SmEncodingMgr"</code>, '
          '<code>"Condition"</code>, <code>"Actions"</code>, <code>"SmWaitText"</code>).',
    'ju': 'Căn lề text: <code>0</code> giữa, <code>2</code> phải, không có = trái.',
    'ro': 'Góc xoay (độ). Mũi tên Pentagon: 270 = chỉ sang phải (thường gặp), 180 lên, 90 trái, 0 xuống.',
    'sl': 'Cờ của hình vẽ (thường 0).' + UNSURE,
    'layer': 'Lớp vẽ.' + UNSURE,
    'ps': 'Chiến lược đặt vị trí so với object cha, vd. <code>"CenterOffsetStrategy"</code>.',
    'stg': 'Chiến lược sắp xếp các text con, vd. <code>"VerticalLayoutStrategy"</code>.',
    'shape': 'Hình vẽ của object (Circle, Rectangle, CompositeShape…). Tâm/vị trí object lấy từ '
             '<code>xt</code> của shape.',
    'optionalChildren': 'Danh sách object con (nút trên diagram, cột/hàng của bảng, phần của hình ghép…).',
    'autoResize': '<code>1</code>: tool cũ tự co giãn khung theo nội dung.',
    'associable': 'Text có thể gắn (associate) với object khác.' + UNSURE,
    'oxt': 'Extent gốc của khung comment/grouping.' + UNSURE,
    'tg': 'Nhóm text tên port (<code>CPTG</code>).',
    'dt': 'Text khai báo port (<code>MLText</code>), vd. <code>"input  wire  clk;"</code>.',
    'thePort': 'Bản sao <code>LogicalPort</code> của port này.',
    'name': 'Tên (thường là một <code>Text</code> có <code>st</code>, hoặc chuỗi).',
    'cond': 'Điều kiện (text).',
    'tline': 'Đường kẻ trên của khối.', 'bline': 'Đường kẻ dưới của khối.',
    'ttri': 'Tam giác trên (nút mở/thu khối).', 'btri': 'Tam giác dưới.',
    'textVec': 'Danh sách text của khối: thường từng cặp <code>Text</code> tiêu đề + <code>MLText</code> nội dung.',
    'first': 'Text tiêu đề của cặp.', 'second': 'Text nội dung của cặp (đọc ra theo tiêu đề, xem import_sm '
                                                '<code>_labelled_texts</code>).',
    'wrapOption': 'Kiểu xuống dòng của text nhiều dòng.' + UNSURE,
    'visibleHeight': 'Chiều cao vùng hiển thị text.', 'visibleWidth': 'Chiều rộng vùng hiển thị text.',
}

# -- types ----------------------------------------------------------------------------------
TYPES: dict[str, dict] = {
    # file and header
    'DocumentHdr': {
        'desc': 'Header của file (khóa top-level <code>Header</code>): phiên bản, ngôn ngữ HDL, '
                'các file include. Trong .sm còn có danh sách machine.',
        'keys': {
            'version': 'Phiên bản cấu trúc header (gặp <code>2</code>).',
            'language': 'Ngôn ngữ HDL: <code>1</code> = Verilog (mọi mẫu đều là 1).' + UNSURE,
            'dialect': 'Phương ngữ: <code>5</code> trong mọi mẫu (Verilog 2001?).' + UNSURE,
            'dmPackageRefs': 'Package được tham chiếu (danh sách, thường rỗng với Verilog).',
            'machine': 'Cây <code>Machine</code>: một machine con cho mỗi ConcurrentSM, cùng thứ tự.',
            'includeRefs': 'Các file <code>`include</code> của module (vd. defines, params).',
            'instances': '.bd: danh sách <code>Instance</code>, một cho mỗi component đặt trên diagram (tên instance, '
                         'thư viện, unit, giá trị tham số). Khớp với <code>SaComponent</code>/<code>MWC</code> qua '
                         '<code>uid</code>.',
            'embeddedInstances': '.bd: tên và số thứ tự của các embedded block (<code>EmbeddedInstance</code>).',
            'frameInstances': '.bd: các generate frame (<code>FrameInstance</code>), mỗi frame có các instance bên trong.',
            'paramInstances': '.bd: tham số của instance.' + UNSURE,
        }},
    'Machine': {
        'desc': 'Tên các state machine trong header. Phần tử thứ i của <code>children</code> ứng với '
                'ConcurrentSM thứ i trong diagram.',
        'keys': {
            'name': 'Tên machine.',
            'children': 'Các machine con.',
            'stateSignalName': 'Tên biến state hiện tại (vd. <code>current_state</code>). import_sm đọc '
                               'làm <code>Machine.current_state_name</code>; <code>SmGenChar csName</code> ưu tiên hơn.',
        }},
    'StateMachine': {
        'desc': 'Gốc model của file .sm (khóa top-level <code>model</code>). Chứa bảng tín hiệu, bảng '
                'tham số, các template mặc định và diagram.',
        'keys': {
            'VExpander': 'Bảng biến môi trường lúc lưu (<code>VariableExpander</code>).',
            'commonDM': 'Bảng tín hiệu (Signals Table): <code>CommonDM</code> chứa các <code>LeafLogPort</code>.',
            'cdmCsm': 'Danh sách bảng tín hiệu theo từng concurrent machine.' + UNSURE,
            'genericsCommonDM': 'Bảng tham số (Parameters): <code>CommonDM</code> chứa các <code>LogGeneric</code>.',
            'signalSuffix': 'Hậu tố của output registered (mặc định <code>"_r"</code>) → '
                            '<code>FsmView.registered_affix</code>.',
            'clockSuffix': 'Hậu tố của output clocked (mặc định <code>"_cld"</code>) → '
                           '<code>FsmView.clocked_affix</code>.',
            'defaultState': 'Template của state mới. export_sm copy nó khi thêm state; import_sm lấy tên mặc định.',
            'defaultWaitState': 'Template của wait state.',
            'defaultCompositeState': 'Template của hierarchical state.',
            'defaultJunction': 'Template của junction (cả ký hiệu mặc định).',
            'defaultTransition': 'Template của transition.',
            'defaultLink': 'Template của link.',
            'defaultClk': 'Template của clock point.', 'defaultRst': 'Template của reset point.',
            'defaultEnable': 'Template của enable point.', 'defaultRecStatePt': 'Template của recovery point.',
            'defaultEntryPoint': 'Template của entry point.', 'defaultExitPoint': 'Template của exit point.',
            'defaultInterruptPoint': 'Template của interrupt point.',
            'activeModelName': 'Tên model đang hoạt động.' + UNSURE,
            'LanguageMgr': 'Bộ quản lý ngôn ngữ. Có chữ <code>SystemVerilog</code> → view SystemVerilog, '
                           'ngược lại Verilog.',
            'lastUid': 'uid lớn nhất đã dùng trong file.',
            'optionalChildren': 'Các ConcurrentSM.',
        }},
    'Symbol': {
        'desc': 'Gốc model của file .sb (khóa top-level <code>model</code>): bảng port, bảng tham số, thân symbol.',
        'keys': {
            'commonDM': 'Bảng port (interface): <code>CommonDM</code> chứa các <code>LogPort</code>.',
            'genericsCommonDM': 'Bảng tham số: <code>LogGeneric</code> (đọc bởi import_sm '
                                '<code>symbol_parameters</code>).',
            'optionalChildren': 'Các object vẽ: <code>SymbolBody</code>, comment…',
            'parentGraphicsRef': 'View đồ họa mà symbol này thuộc về (<code>HdmGraphicsRef</code>).',
            'defaultSymbolBody': 'Template thân symbol.', 'defaultCptPort': 'Template port.',
            'defaultCptPortProtocol': 'Template port kiểu protocol.', 'defaultCptPortBuffer': 'Template port buffer.',
            'DeclarativeBlock': 'Khối text khai báo (<code>SymDeclBlock</code>).',
            'okToSyncOnLoad': 'Cho phép đồng bộ port khi mở.' + UNSURE,
            'OkToSyncGenericsOnLoad': 'Cho phép đồng bộ tham số khi mở.' + UNSURE,
            'postModuleDirective': 'Directive sau module.' + UNSURE,
            'lastUid': 'uid lớn nhất đã dùng trong file.',
        }},
    'StateDiagram': {
        'desc': 'Một trang diagram: <code>topDiagram</code> của ConcurrentSM, hoặc <code>childDiagram</code> '
                'của CompositeState. Các nút nằm trong <code>optionalChildren</code>. Diagram đầu còn giữ các '
                'khối khai báo và thiết lập trang.',
        'keys': {
            'optionalChildren': 'Các nút: State, CompositeState, Junction, Link, Transition, các point, comment…',
            'viewArea': 'Vùng đang xem <code>"x0,y0,x1,y1"</code> → <code>Machine.view_area</code> '
                        '(mở lại diagram đúng chỗ tool cũ đang xem).',
            'windowSize': 'Kích thước cửa sổ lúc lưu.', 'cachedDiagramExtent': 'Extent của cả diagram.',
            'grid': 'Lưới (<code>Grid</code>).', 'bg': 'Màu nền.',
            'packageList': 'Khối package.', 'compDirBlock': 'Khối Compiler Directives (pre/post/end-module).',
            'localDecl': 'Khối Module Declarations.', 'processDecl': 'Khối khai báo trong process.',
            'defaultActions': 'Global Actions (Pre / Post Actions).',
            'archConcurrentStatementBlock': 'Khối Concurrent Statements.',
            'signalsGenStatus': 'Khối Signal Status.', 'stateRegBlock': 'Khối State Register Statements.',
            'isTopLevel': '<code>1</code> ở diagram trên cùng.',
            'pageSetupInfo': 'Thiết lập in.', 'LanguageMgr': 'Như ở <code>StateMachine</code>.',
        }},
    'VariableExpander': {'desc': 'Danh sách biến môi trường tool cũ ghi lúc lưu (<code>vvMap</code>).',
                         'keys': {'vvMap': 'Danh sách <code>vvPair</code>.'}},
    'vvPair': {'desc': 'Một biến: thư mục HDL/thư mục đồ họa, tên unit, user, host, ngày giờ lưu… Thay đổi mỗi '
                       'lần lưu, không ảnh hưởng tới thiết kế. HDL Studio giữ nguyên.',
               'keys': {'variable': 'Tên biến.', 'value': 'Giá trị (đường dẫn, tên… — bị che trong trang này).'}},
    'HdmGraphicsRef': {'desc': 'Tham chiếu tới một view: thư viện, unit, view.',
                       'keys': {'libraryName': 'Thư viện.', 'entityName': 'Unit.', 'viewName': 'View.'}},
    'Grid': {'desc': 'Lưới của trang vẽ.'},
    'PageSetupInfo': {'desc': 'Thiết lập in và xuất (khổ giấy, lề, hướng giấy…). HDL Studio không dùng, giữ nguyên.'},

    # state machine
    'ConcurrentSM': {
        'desc': 'Một state machine (một file .sm có thể có nhiều machine chạy song song). '
                'import_sm tạo một <code>model.Machine</code> cho mỗi object.',
        'keys': {
            'name': 'Tên machine.',
            'topDiagram': 'Diagram của machine (<code>StateDiagram</code>).',
            'genChar': 'Thiết lập sinh code (<code>SmGenChar</code>).',
            'encoding': 'Thiết lập state encoding của machine (<code>Encoding</code>, xem chủ đề '
                        '<a href="#topic-encoding">State encoding</a>). <b>import_sm chưa đọc.</b>',
            'stateOrder': 'Thứ tự state <code>[&amp;N …]</code>: thứ tự gán mã encoding. import_sm sắp '
                          '<code>Machine.states</code> theo thứ tự này.',
        }},
    'SmGenChar': {
        'desc': 'Thiết lập sinh code của một machine (State Machine Properties).',
        'keys': {
            'casePragma': 'Pragma cho câu <code>case</code> (full_case / parallel_case…).' + UNSURE,
            'nextStateClocking': '<code>1</code>: next state được clock → <code>Machine.next_state_clocking</code>.',
            'csName': 'Tên biến current state (Advanced > State Signal Names) → '
                      '<code>Machine.current_state_name</code>.',
            'nsName': 'Tên biến next state → <code>Machine.next_state_name</code>.',
        }},
    'Encoding': {
        'desc': 'State encoding của một machine (State Machine Properties > Encoding). Xem chủ đề '
                '<a href="#topic-encoding">State encoding</a>.',
        'keys': {
            'scheme': 'Scheme đang dùng. Encoding có hiệu lực là <code>style</code> của pair có cùng số scheme '
                      '(gặp 0 và 3).' + UNSURE,
            'encodingStyles': 'Mỗi scheme 0…5 một <code>(pair scheme S style N)</code>. Đổi sang 1-Hot làm '
                              '<code>(pair scheme 0 …)</code> đổi <code>style 0 → 1</code>.',
            'otherValues': 'Mỗi scheme một <code>(pair scheme S otherValue "…")</code>: giá trị nhánh '
                           '“others”/default.' + UNSURE,
            'attribute': 'Sinh attribute encoding cho synthesis.' + UNSURE,
            'synSafe': 'Máy trạng thái “safe” (thêm nhánh phục hồi).' + UNSURE,
            'outputEncodedLocals': 'Xuất biến local đã mã hóa.' + UNSURE,
            'useVerilogParameterRange': 'Khai báo parameter có range.' + UNSURE,
            'radix': 'Luôn là <code>2</code> trong mẫu, nhưng code sinh ra dùng <code>\'d</code> (sequential) '
                     'lẫn <code>\'b</code> (one-hot), nên không quyết định cơ số của literal.' + UNSURE,
        }},
    'pair': {'desc': 'Phần tử của <code>Encoding encodingStyles</code> / <code>otherValues</code>.',
             'keys': {'scheme': 'Số scheme (0…5).', 'style': 'Kiểu mã: <code>1</code> = 1-Hot (đã xác minh).',
                      'otherValue': 'Giá trị nhánh others của scheme.'}},
    'State': {
        'desc': 'Một state. Tâm lấy từ <code>shape</code> (Circle, hoặc CircleInOctagon với wait state).',
        'keys': {
            'name': 'Tên state (<code>Text st</code>).',
            'wait': 'Text của wait state (số chu kỳ chờ). Text ẩn mặc định khi không phải wait state.',
            'isWait': '<code>1</code>: wait state.',
            'encoding': 'Mã của state khi encoding thủ công (<code>Text</code>, <code>tm "SmEncodingMgr"</code>; '
                        'giá trị ở <code>st</code>, không có <code>st</code> = không đặt). → <code>State.encoding</code>.',
            'actionBlk': 'Khối action (<code>SmStateActionsBlock</code>).',
            'caseExpr': 'Biểu thức case của state.' + UNSURE,
            'useCase': 'Dùng câu case cho state.' + UNSURE,
            'caseSettings': 'Thiết lập case (<code>CaseSettings</code>).',
        }},
    'SmStateActionsBlock': {
        'desc': 'Khối action gắn với một state. import_sm giữ vị trí và kích thước để vẽ đúng chỗ.',
        'keys': {'entryActions': 'Entry actions (MLText).', 'inActions': 'Actions trong state (MLText).',
                 'exitActions': 'Exit actions (MLText).'}},
    'CompositeState': {'desc': 'Hierarchical state: diagram con ở <code>childDiagram</code>, nối qua '
                               'EntryPoint / ExitPoint.',
                       'keys': {'childDiagram': 'Diagram con (<code>StateDiagram</code>).', 'name': 'Tên.'}},
    'EntryPoint': {'desc': 'Điểm vào của hierarchical state (nằm trong diagram con).'},
    'ExitPoint': {'desc': 'Điểm ra của hierarchical state.'},
    'Junction': {
        'desc': 'Junction (điểm rẽ nhánh if hoặc case).',
        'keys': {'jType': '<code>1</code> = case, không có = if.',
                 'caseExpr': 'Biểu thức case, dạng <code>"CASE: expr"</code>.',
                 'symbol': 'Ký hiệu hiển thị trên junction.', 'name': 'Tên.',
                 'caseSettings': 'Thiết lập case.'}},
    'Link': {'desc': 'Link tới một state khác (thay cho đường transition dài).',
             'keys': {'name': 'Tên state đích (<code>Text st</code>).'}},
    'Transition': {
        'desc': 'Một transition giữa hai nút.',
        'keys': {'start': 'Nút đầu (<code>&amp;N</code>).', 'end': 'Nút cuối (<code>&amp;N</code>).',
                 'shape': 'Đường vẽ (<code>Spline</code> / <code>PolyLine</code>, <code>pts</code>: đầu, điểm gãy, cuối).',
                 'tb': 'Khối điều kiện + action (<code>TransitionBlock</code>).',
                 'tp': 'Vòng tròn độ ưu tiên (<code>TransitionPriority</code>).',
                 'cond': 'Điều kiện thô.' + UNSURE,
                 'ss': 'Kiểu gắn ở đầu đường.' + UNSURE, 'es': 'Kiểu gắn ở cuối đường.' + UNSURE}},
    'TransitionBlock': {
        'desc': 'Khung điều kiện và action của transition.',
        'keys': {'condition': 'Điều kiện (MLText <code>st</code>).',
                 'actions': 'Action (MLText). <code>"&lt; Automatic &gt;"</code> = không có action.',
                 'lineShape': 'Đường kẻ giữa điều kiện và action.'}},
    'TransitionPriority': {'desc': 'Vòng tròn số ưu tiên của transition.',
                           'keys': {'pr': 'Độ ưu tiên (Text, 1 = cao nhất).', 'padding': 'Khoảng đệm.'}},
    'SmResetPoint': {'desc': 'Reset point. Hình sóng (OrthoPolyLine) là reset bất đồng bộ, vòng tròn là đồng bộ.',
                     'keys': {'cond': 'Điều kiện reset.', 'prio': 'Độ ưu tiên.', 'actions': 'Action khi reset.',
                              'level': 'Mức tích cực.' + UNSURE, 'mode': 'Đồng bộ / bất đồng bộ.' + UNSURE}},
    'SmClockPoint': {'desc': 'Clock point: tín hiệu clock của machine.', 'keys': {'cond': 'Biểu thức clock.'}},
    'SmEnablePoint': {'desc': 'Enable point.', 'keys': {'cond': 'Biểu thức enable.', 'level': 'Mức tích cực.'}},
    'SmRecoveryStatePoint': {'desc': 'Recovery state point.'},
    'InterruptPoint': {'desc': 'Interrupt point.'},
    'SmControlCondition': {'desc': 'Khung điều kiện của clock / reset / enable point.'},
    'CaseSettings': {'desc': 'Thiết lập câu case của state / junction.',
                     'keys': {'varName': 'Tên biến case.', 'pragma': 'Pragma.' + UNSURE}},

    # symbol
    'SymbolBody': {'desc': 'Thân symbol: hình chữ nhật và các port (<code>CptPort</code>) trong '
                           '<code>optionalChildren</code>.',
                   'keys': {'gi': 'Khung tham số (<code>GenericInterface</code>).',
                            'biTextGroup': 'Tên thư viện / unit hiển thị trên thân.',
                            'portVis': 'Thiết lập hiển thị port (<code>PortSigDisplay</code>).'}},
    'CptPort': {'desc': 'Trong .sb: một port vẽ trên thân symbol. Input ở cạnh trái, output/inout ở cạnh phải, '
                        'cách nhau 1000 (xem chủ đề <a href="#topic-symbol">Port của symbol</a>). Trong .bd: một '
                        'pin của component (<code>SaComponent</code> / <code>MWC</code>); dây nối vào nó bằng '
                        '<code>Wire start/end &amp;N</code>.',
                'keys': {'shape': 'Tam giác chỉ hướng.',
                         'cm': 'Cờ port.' + UNSURE}},
    'CptPortProtocol': {'desc': 'Port kiểu protocol (bus nhóm).'},
    'CPTG': {'desc': 'Text tên port trên symbol.',
             'keys': {'f': 'Text: <code>"name"</code> hoặc <code>"name : [7:0]"</code>.'}},
    'LogPort': {'desc': 'Một dòng của bảng port trong .sb (tương ứng LeafLogPort trong .sm).',
                'keys': {'port': '<code>LogicalPort</code> của port.'}},
    'PortSigDisplay': {'desc': 'Port hiển thị gì trên symbol.' + UNSURE},
    'GenericInterface': {'desc': 'Khung liệt kê tham số trên symbol.'},
    'Matrix': {'desc': 'Bảng text của khung tham số.'},
    'SymDeclBlock': {'desc': 'Khối text khai báo của symbol.'},
    'FFT': {'desc': 'Dấu clock (tam giác flip-flop) trên port. import_bd dùng nó để nhận ra pin clock.'},

    # block diagram
    'BlockDiag': {
        'desc': 'Gốc model của file .bd (khóa top-level <code>model</code>): bảng net, bảng tham số, các object vẽ '
                'và các template. import_bd đọc thành <code>bd_model.BlockDiagram</code>.',
        'keys': {
            'optionalChildren': 'Mọi object vẽ: component, wire, port I/O, embedded block, frame, junction, comment…',
            'commonDM': 'Bảng net / port (Signals Table): <code>CommonDM</code> chứa các <code>LeafLogPort</code>.',
            'genericsCommonDM': 'Bảng tham số: <code>LogGeneric</code>.',
            'viewArea': 'Vùng đang xem → <code>BlockDiagram.view_area</code>.',
            'archDeclarativeBlock': 'Khối Declarations (<code>BdArchDeclBlock</code>).',
            'compDirBlock': 'Khối Compiler Directives.',
            'frameCount': 'Số generate frame.' + UNSURE,
            'lastUid': 'uid lớn nhất đã dùng trong file.',
            'LanguageMgr': 'Như ở <code>StateMachine</code>: có <code>SystemVerilog</code> → view SystemVerilog.',
            'defaultSaComponent': 'Template component. Mọi object dưới <code>default*</code> là template, '
                                  'import_bd bỏ qua.',
        }},
    'Wire': {
        'desc': 'Một đoạn dây nối hai object (pin của component, port I/O, embedded block, junction). Dây mang một '
                'net (<code>on</code>).',
        'keys': {
            'on': 'Net của dây (<code>&amp;N</code> → <code>Net</code>).',
            'start': 'Object ở đầu dây (<code>&amp;N</code>: CptPort, PortIo…, HdlText, BdJunction).',
            'end': 'Object ở cuối dây.',
            'shape': 'Đường vẽ (<code>OrthoPolyLine pts</code>).',
            'sl': 'Slice của net mà dây mang, vd. <code>"[3:0]"</code>.',
            'tg': 'Nhóm text tên dây (<code>WTG</code>; text có <code>tm "WireNameMgr"</code>).',
            'sat': 'Kiểu gắn ở đầu dây.' + UNSURE, 'eat': 'Kiểu gắn ở cuối dây.' + UNSURE,
            'sty': 'Kiểu dây (signal / bus).' + UNSURE,
            'si': 'Chỉ số dây.' + UNSURE, 'st': 'Trạng thái dây.' + UNSURE,
        }},
    'Net': {'desc': 'Một net (tín hiệu nối các dây). Tên ở <code>decl n</code>.',
            'keys': {'decl': 'Khai báo (<code>Decl</code>): tên, kiểu, range.', 'declText': 'Text khai báo.'}},
    'WTG': {'desc': 'Nhóm text tên của một dây.'},
    'WWL': {'desc': 'Nhãn của dây.' + UNSURE},
    'SaComponent': {
        'desc': 'Một instance component đặt trên diagram. Pin là các <code>CptPort</code> trong '
                '<code>optionalChildren</code>.',
        'keys': {
            'ttg': 'Các text: thư viện (<code>tm "BdLibraryNameMgr"</code>), unit (<code>"CptNameMgr"</code>), '
                   'tên instance (<code>"InstanceNameMgr"</code>).',
            'ga': 'Khung tham số của instance (<code>GenericAssociation</code>).',
            'portVis': 'Hiển thị port (<code>PortSigDisplay</code>).',
            'connectByName': 'Nối theo tên.' + UNSURE,
            'viewicon': 'Biểu tượng loại view.', 'archFileType': 'Loại file của view.' + UNSURE,
        }},
    'MWC': {'desc': 'Component ModuleWare (cổng logic có sẵn, vd. and / or / mux). import_bd đặt thư viện '
                    '<code>moduleware</code>.',
            'keys': {'prms': 'Tham số của cổng.' + UNSURE}},
    'mwParamsVisibilityOptions': {'desc': 'Hiển thị tham số của ModuleWare.'},
    'Instance': {'desc': 'Một instance trong <code>Header instances</code>.',
                 'keys': {'name': 'Tên instance.', 'duLibraryName': 'Thư viện.', 'duName': 'Unit.',
                          'elements': 'Giá trị tham số (<code>GiElement</code>).',
                          'mwi': '<code>1</code>: instance ModuleWare.' + UNSURE,
                          'uid': 'uid của SaComponent / MWC tương ứng.'}},
    'EmbeddedInstance': {'desc': 'Tên và số thứ tự của một embedded block, theo thứ tự các <code>HdlText</code>.'},
    'FrameInstance': {'desc': 'Một generate frame trong header: các instance bên trong (<code>insts</code>).'},
    'HdlText': {'desc': 'Embedded block: khung chứa code HDL viết tay (<code>EmbeddedText</code>).'},
    'EmbeddedText': {'desc': 'Code HDL của embedded block (<code>commentText</code>).'},
    'PortIoIn': {'desc': 'Port input của module vẽ trên diagram. Tên lấy từ net của dây nối vào.'},
    'PortIoOut': {'desc': 'Port output của module vẽ trên diagram.'},
    'PortIoInOut': {'desc': 'Port inout của module vẽ trên diagram.'},
    'PortIoBuffer': {'desc': 'Port buffer (template).'},
    'PortIoSlave': {'desc': 'Port slave của protocol (template).'},
    'PortIoMaster': {'desc': 'Port master của protocol (template).'},
    'Frame': {'desc': 'Generate frame: FOR (không có <code>style</code>), IF (<code>style 1</code>), ELSE '
                      '(<code>style 2</code>). Tiêu đề <code>"name: spec"</code>.',
              'keys': {'style': 'Không có = FOR, 1 = IF, 2 = ELSE.', 'lb': 'Cận trái của FOR.',
                       'rb': 'Cận phải của FOR.', 'seqNum': 'Số thứ tự frame (<code>FrameSequenceNumber</code>).',
                       'title': 'Tiêu đề.', 'decls': 'Khai báo trong frame.'}},
    'FrameSequenceNumber': {'desc': 'Số thứ tự của generate frame.'},
    'BdJunction': {'desc': 'Chấm nối nơi các dây của cùng net gặp nhau.'},
    'GenericAssociation': {'desc': 'Khung liệt kê giá trị tham số của một instance.'},
    'Parameter': {'desc': 'Tham số (tên, giá trị).', 'keys': {'name': 'Tên.', 'val': 'Giá trị.'}},
    'Property': {'desc': 'Thuộc tính gắn với object.' + UNSURE},
    'Blk': {'desc': 'Block (template).'},
    'VhdlComponent': {'desc': 'Component VHDL (template).'},
    'VerilogComponent': {'desc': 'Component Verilog (template).'},
    'GlobalConnector': {'desc': 'Global connector (template).'},
    'Ripper': {'desc': 'Ripper tách bit từ bus (template).'},
    'Bundle': {'desc': 'Bundle (template).'},
    'Protocol': {'desc': 'Protocol (template).'},
    'PortMapFrame': {'desc': 'Port map frame (template).'},
    'BdArchDeclBlock': {
        'desc': 'Khối Declarations của block diagram.',
        'keys': {'preUserText': 'Khai báo người dùng đặt trước → <code>BlockDiagram.pre_user_declarations</code>.',
                 'postUserText': 'Khai báo người dùng đặt sau → <code>post_user_declarations</code>.',
                 'declLabel': 'Tiêu đề khối (vị trí, ẩn/hiện).', 'portLabel': 'Nhãn phần port.',
                 'diagSignalLabel': 'Nhãn phần tín hiệu của diagram.'}},
    'CommentGraphic': {'desc': 'Hình vẽ trang trí (comment graphic).'},
    'Hexagon': {'desc': 'Hình lục giác.'},
    'Line2D': {'desc': 'Đoạn thẳng (comment graphic).'},
    'PolyLine2D': {'desc': 'Đường gấp khúc (comment graphic).'},

    # tables
    'LeafLogPort': {
        'desc': 'Một dòng của Signals Table trong .sm (port hoặc tín hiệu nội bộ), hoặc của bảng net trong .bd. import_sm đọc thành '
                '<code>model.Signal</code>; export_sm ghi lại. Mã số xem chủ đề '
                '<a href="#topic-signals">Bảng tín hiệu</a>.',
        'keys': {'port': '<code>LogicalPort</code>: mode và khai báo.',
                 'cat': 'Loại tín hiệu (clock / reset / enable…), không có = Data.',
                 'expr': 'Biểu thức của clock / reset / enable.',
                 'scheme': 'Kiểu gán output: không có = combinational, <code>1</code> clocked, '
                           '<code>2</code> registered.',
                 'ass': '<code>"&lt;none&gt;"</code>: không gán (scheme none).',
                 'defVal': 'Giá trị mặc định.', 'rstVal': 'Giá trị reset.'}},
    'LogicalPort': {'desc': 'Mode và khai báo của một port / tín hiệu.',
                    'keys': {'m': 'Mode: không có = input, <code>1</code> output, <code>2</code> inout, '
                                  '<code>4</code> local (tín hiệu nội bộ).',
                             'decl': 'Khai báo (<code>Decl</code>).', 'lang': 'Ngôn ngữ.',
                             'protocolPorts': 'Các port con của port protocol.'}},
    'Decl': {'desc': 'Khai báo một tín hiệu.',
             'keys': {'n': 'Tên.', 't': 'Kiểu (wire, reg, logic…).', 'b': 'Range, vd. <code>"[7:0]"</code>.',
                      's': '<code>1</code>: signed.', 'o': 'Thứ tự port (1, 2…): input, rồi output, rồi inout, '
                                                           'mỗi nhóm theo tên.',
                      'eolc': 'Comment cuối dòng (không có <code>//</code>).', 'iv': 'Giá trị khởi tạo.',
                      'ub': 'Chiều unpacked array.', 'suid': 'uid trong bảng của symbol.',
                      'pr': 'Pragma.' + UNSURE, 'prec': 'Text trước khai báo.' + UNSURE,
                      'preAdd': 'Thêm trước.' + UNSURE, 'posAdd': 'Thêm sau.' + UNSURE}},
    'LogGeneric': {'desc': 'Một dòng của bảng tham số.', 'keys': {'generic': 'Tham số (<code>GiElement</code>).'}},
    'GiElement': {'desc': 'Một tham số (parameter).',
                  'keys': {'name': 'Tên.', 'type': 'Kiểu.', 'value': 'Giá trị mặc định.', 'e': 'Comment.' + UNSURE}},
    'LGroup': {'desc': 'Một nhóm tín hiệu trong Signals Table (dòng tiêu đề nhóm).',
               'keys': {'name': 'Tên nhóm.', 'comment': 'Comment.', 'optionalChildren': 'Các tín hiệu trong nhóm.'}},
    'CommonDM': {'desc': 'Một bảng (tín hiệu, port hoặc tham số): phần logic (<code>ldm</code>) + phần hiển thị '
                         '(<code>pdm</code>).',
                 'keys': {'ldm': '<code>LogicalDM</code>: các dòng.', 'pdm': '<code>PhysicalDM</code>: cách hiển thị.'}},
    'LogicalDM': {'desc': 'Danh sách logic: tiêu đề cột và các dòng (LeafLogPort / LogPort / LogGeneric / LGroup).'},
    'PhysicalDM': {'desc': 'Phần hiển thị của bảng: Sheet.'},
    'Sheet': {'desc': 'Bảng hiển thị: hàng (<code>SheetRow</code>) và cột (<code>SheetCol</code>). Đọc bởi '
                      '<code>formats/sheet.py</code> (độ rộng cột, thứ tự…).'},
    'SheetRow': {'desc': 'Danh sách hàng: mỗi hàng một <code>MRCItem</code>; <code>emptyMRCItem</code> là hàng trống cuối.'},
    'SheetCol': {'desc': 'Danh sách cột: mỗi cột một <code>MRCItem</code>.'},
    'MRCItem': {'desc': 'Một hàng hoặc cột hiển thị.',
                'keys': {'litem': 'Phần tử logic (<code>&amp;N</code>).', 'pos': 'Vị trí hiển thị (0…).',
                         'dimension': 'Chiều cao hàng / độ rộng cột.', 'hidden': '<code>1</code>: ẩn.'}},
    'PVME': {'desc': 'Thuộc tính hiển thị riêng của một ô (hàng, cột).'},
    'MVa': {'desc': 'Thuộc tính hiển thị của ô: màu, font, căn lề.'},

    # text
    'Text': {'desc': 'Text một dòng.'},
    'MLText': {'desc': 'Text nhiều dòng (action, điều kiện, khai báo…).'},
    'TextAssociate': {'desc': 'Text gắn với object (vd. tên junction).', 'keys': {'text': 'Text.'}},
    'BiTextGroup': {'desc': 'Cặp text tiêu đề + nội dung (vd. "State Register Statements" + MLText).'},
    'MlTextGroup': {'desc': 'Nhóm nhiều text.'},
    'PackageList': {'desc': 'Khối khai báo package.'},
    'SmLocalDecl': {'desc': 'Khối Module Declarations.'},
    'SmProcessDecl': {'desc': 'Khối khai báo trong process.'},
    'SmSignalGenStatus': {'desc': 'Khối Signal Status.'},
    'CommentText': {'desc': 'Khung comment trên diagram.'},
    'RequirementText': {'desc': 'Text requirement (template).'},
    'Panel': {'desc': 'Panel (vùng in) trên diagram.'},

    # shapes
    'VaSet': {
        'desc': 'Thuộc tính hiển thị của một object.',
        'keys': {'vasetType': 'Loại tập thuộc tính (1 hình, 3 đường…).' + UNSURE,
                 'fg': 'Màu chữ / nét <code>"r,g,b"</code>, mỗi thành phần 0…65535.',
                 'bg': 'Màu nền <code>"r,g,b"</code> (0…65535).', 'lineColor': 'Màu đường.',
                 'lineWidth': 'Độ dày nét.', 'lineStyle': 'Kiểu nét.', 'fillStyle': 'Kiểu tô.',
                 'font': 'Font <code>"tên,cỡ,đậm"</code>, vd. <code>"courier,8,1"</code>.',
                 'isHidden': '<code>1</code>: object bị ẩn.', 'transparent': 'Nền trong suốt.'}},
    'Circle': {'desc': 'Hình tròn (state).', 'keys': {'radius': 'Bán kính → <code>State.radius</code>.'}},
    'CircleInOctagon': {'desc': 'Hình của wait state.'},
    'Pentagon': {'desc': 'Hình mũi tên (link, point).'},
    'Diamond': {'desc': 'Hình thoi (junction).'},
    'Spline': {'desc': 'Đường cong (transition).', 'keys': {'arrow': '<code>1</code>: có mũi tên.'}},
    'PolyLine': {'desc': 'Đường gấp khúc.', 'keys': {'arrow': '<code>1</code>: có mũi tên.'}},
    'OrthoPolyLine': {'desc': 'Đường gấp khúc vuông góc (hình sóng của reset bất đồng bộ).'},
    'Line': {'desc': 'Đoạn thẳng.'},
    'Rectangle': {'desc': 'Hình chữ nhật (khung action, khung điều kiện, thân symbol…).'},
    'Triangle': {'desc': 'Tam giác (hướng port trên symbol, nút mở/thu khối).'},
    'CompositeShape': {'desc': 'Hình ghép từ nhiều hình con (<code>optionalChildren</code>), vd. reset point.'},
    'Arc2D': {'desc': 'Cung tròn.'},
    'CustomPolygon': {'desc': 'Đa giác tự do.'},
    'TripleCircle': {'desc': 'Ba vòng tròn lồng nhau (hình của hierarchical state).' + UNSURE},
    'RectFrame': {'desc': 'Khung chữ nhật của panel.'},
    'ZoomableIcon': {'desc': 'Biểu tượng bitmap phóng to được (<code>iconName</code>).'},
    'Grouping': {'desc': 'Nhóm các object vẽ (Group).'},
    'GroupingShape': {'desc': 'Khung của nhóm.'},
    'LEmptyRow': {'desc': 'Hàng trống cuối bảng (để thêm dòng mới).'},
}
for _t in CATEGORY_OF['table'].split():
    if _t.endswith('ColHdr'):
        TYPES.setdefault(_t, {'desc': 'Tiêu đề một cột của bảng tín hiệu / port / tham số (<code>tm</code> = tên cột).'})
    elif _t.endswith('RowHdr'):
        TYPES.setdefault(_t, {'desc': 'Hàng tiêu đề / hàng lọc / nhãn của bảng.'})
TYPES.setdefault('ColumnHdr', {'desc': 'Tiêu đề cột của bảng.'})

# -- topics ---------------------------------------------------------------------------------
TOPICS = [
    ('modes', 'Hai chế độ làm việc', '''
<p>HDL Studio cho người dùng hai lựa chọn:</p>
<ol>
<li><b>Import <code>.hdp</code>, sau đó dùng định dạng của HDL Studio</b> (<code>&lt;view&gt;.fsm.json</code>,
<code>struct.bd.json</code>…). File của tool cũ chỉ được đọc một lần khi import.</li>
<li><b>Dùng luôn định dạng của tool cũ</b>: đọc và ghi trực tiếp <code>.sm</code>, <code>.sb</code>, <code>.bd</code>,
để tool cũ và HDL Studio cùng mở được một file.</li>
</ol>
<p>Hiện tại: <code>.sm</code> được ghi lại tại chỗ (kèm <code>symbol.sb</code> khi port đổi); <code>.bd</code> mới chỉ
đọc, block diagram lưu thành <code>struct.bd.json</code> cạnh file <code>.bd</code>.</p>
<p>Vì vậy mỗi tính năng của model phải đi được cả hai chiều với file của tool cũ: import đọc đủ, export ghi lại
đúng chỗ, và giữ nguyên mọi thứ HDL Studio không mô hình hóa. Trang này là bản đồ để làm việc đó.</p>
'''),
    ('syntax', 'Cú pháp chung', '''
<p>Cả <code>.sm</code>, <code>.sb</code> và <code>.bd</code> là cùng một dạng S-expression, đọc/ghi bởi
<code>src/formats/sexpr.py</code>:</p>
<pre>file    := (key value)*                         ; các khóa top-level
value   := int | atom | "string" | object | list | label object | ref
object  := "(" TypeName (key value)* ")"
list    := "[" value* "]"
label   := *N        ; đặt nhãn cho object ngay sau nó
ref     := &amp;N        ; tham chiếu tới object có nhãn *N</pre>
<ul>
<li><b>int</b>: số nguyên viết chuẩn (<code>0</code>, <code>-40150</code>). <b>atom</b>: token không có ngoặc kép
(<code>2742,0</code>, <code>-40150,216000</code>, tên chiến lược). <b>string</b>: trong ngoặc kép, <code>\\</code>
để escape, có thể nhiều dòng.</li>
<li>Mỗi khóa một dòng; object mở trên dòng của khóa và đóng <code>)</code> trên dòng riêng. Danh sách có thể chứa
dòng trống (được giữ lại).</li>
<li>Khóa có thể lặp lại trong một object. <b>Thứ tự khóa có ý nghĩa</b>: tool cũ đọc theo thứ tự (vd.
<code>st</code> phải đứng trước <code>tm</code>). Khóa mới phải chèn đúng chỗ (export_sm <code>_PLACE</code>,
export_sb <code>_set(after=…)</code>).</li>
<li>Khóa không có = giá trị mặc định (thường 0 hoặc rỗng). Ví dụ <code>LogicalPort</code> không có <code>m</code>
là input.</li>
<li>Đọc rồi ghi lại không sửa gì thì ra đúng từng byte (giữ cả kiểu xuống dòng của file).</li>
</ul>
'''),
    ('layout', 'Cấu trúc file', '''
<p>Cả ba loại file có cùng các khóa top-level (.bd có thêm <code>noEmbeddedEditors</code> trước
<code>model</code>):</p>
<table><tr><th>Khóa</th><th>Giá trị</th></tr>
<tr><td><code>DocumentHdrVersion</code></td><td><code>"1.1"</code></td></tr>
<tr><td><code>Header</code></td><td><code>(DocumentHdr …)</code>: ngôn ngữ, include; trong .sm có thêm cây <code>Machine</code></td></tr>
<tr><td><code>version</code></td><td>phiên bản định dạng, vd. <code>"27.1"</code></td></tr>
<tr><td><code>appVersion</code></td><td>phiên bản tool đã lưu file</td></tr>
<tr><td><code>model</code></td><td><code>(StateMachine …)</code> trong .sm, <code>(Symbol …)</code> trong .sb,
<code>(BlockDiag …)</code> trong .bd</td></tr></table>
<h3>.sm</h3>
<pre>model (StateMachine
  VExpander (VariableExpander vvMap [(vvPair variable value) …])
  commonDM (CommonDM ldm (LogicalDM … LeafLogPort …) pdm (PhysicalDM Sheet …))   ; Signals Table
  genericsCommonDM (CommonDM … LogGeneric …)                                    ; Parameters
  optionalChildren [
    (ConcurrentSM name genChar (SmGenChar) encoding (Encoding) stateOrder [&amp;N …]
      topDiagram (StateDiagram optionalChildren [
        *N (State …)  (CompositeState childDiagram (StateDiagram …))
        (Junction …)  (Link …)  (SmResetPoint …)  (SmClockPoint …)
        (Transition start &amp;N end &amp;N tb (TransitionBlock …) tp (TransitionPriority …))
        …]))]
  defaultState / defaultTransition / … (template cho object mới)
  signalSuffix clockSuffix lastUid LanguageMgr …)</pre>
<h3>.sb</h3>
<pre>model (Symbol
  commonDM (CommonDM … LogPort …)              ; bảng port
  genericsCommonDM (CommonDM … LogGeneric …)   ; bảng tham số
  optionalChildren [
    (SymbolBody shape (Rectangle) optionalChildren [
      (CptPort tg (CPTG f …) dt (MLText …) thePort (LogicalPort …) shape (Triangle) …) …]
      gi (GenericInterface …) …)
    (CommentText …) …]
  parentGraphicsRef (HdmGraphicsRef libraryName entityName viewName)
  DeclarativeBlock (SymDeclBlock …)  defaultCptPort …  lastUid …)</pre>
<h3>.bd</h3>
<pre>Header (DocumentHdr … instances [(Instance name duLibraryName duName elements [(GiElement …)] uid)]
                      embeddedInstances [(EmbeddedInstance name number)] frameInstances [(FrameInstance insts […])])
noEmbeddedEditors …
model (BlockDiag
  commonDM (CommonDM … LeafLogPort …)          ; bảng net / port
  genericsCommonDM (CommonDM … LogGeneric …)   ; bảng tham số
  optionalChildren [
    *N (Net decl (Decl n t b))
    *N (SaComponent ttg (MlTextGroup …) ga (GenericAssociation …) optionalChildren [*N (CptPort thePort …) …])
    *N (MWC …)  *N (HdlText optionalChildren [(EmbeddedText commentText …)])
    *N (PortIoIn …)  *N (PortIoOut …)  *N (BdJunction …)  (Frame title seqNum lb rb style …)
    (Wire on &amp;Net start &amp;N end &amp;N sl "[3:0]" shape (OrthoPolyLine pts […]) tg (WTG …))
    (CommentText …) (Grouping …) …]
  archDeclarativeBlock (BdArchDeclBlock preUserText postUserText …)
  defaultSaComponent / defaultPortIoIn / … (template)  viewArea lastUid LanguageMgr …)</pre>
'''),
    ('units', 'Đơn vị và giá trị thường gặp', '''
<table><tr><th>Giá trị</th><th>Dạng</th><th>Ghi chú</th></tr>
<tr><td>Tọa độ</td><td>số nguyên, trục y hướng xuống</td><td>khoảng 75 đơn vị = 1 pixel ở zoom 100%
(<code>import_sm.SCALE = 1/75</code>). Có thể âm.</td></tr>
<tr><td><code>xt</code></td><td><code>"x0,y0,x1,y1"</code></td><td>hình chữ nhật bao. Tâm của state = tâm
<code>xt</code> của shape.</td></tr>
<tr><td><code>pts</code></td><td><code>["x,y" …]</code></td><td>điểm đầu, các điểm gãy, điểm cuối</td></tr>
<tr><td><code>uid</code></td><td><code>N,0</code></td><td>duy nhất trong file, <code>lastUid</code> giữ số lớn nhất</td></tr>
<tr><td><code>*N</code> / <code>&amp;N</code></td><td>nhãn / tham chiếu</td><td>N độc lập với uid; transition, stateOrder,
MRCItem tham chiếu object bằng <code>&amp;N</code>. HDL Studio đặt id <code>n&lt;N&gt;</code> cho object đọc từ file.</td></tr>
<tr><td>Màu</td><td><code>"r,g,b"</code></td><td>mỗi thành phần 0…65535 (vd. <code>"0,32768,49152"</code>)</td></tr>
<tr><td>Font</td><td><code>"tên,cỡ,đậm"</code></td><td><code>"courier,8,1"</code>, <code>"arial,8,0"</code></td></tr>
<tr><td>Ẩn/hiện</td><td><code>va (VaSet isHidden 1)</code></td><td>object vẫn có trong file nhưng không vẽ</td></tr>
</table>
'''),
    ('encoding', 'State encoding', '''
<p>Lưu trong <b>.sm</b>, không có trong .sb. Có hai chỗ:</p>
<h3>1. Kiểu encoding của machine: <code>ConcurrentSM encoding (Encoding …)</code></h3>
<pre>encoding (Encoding
scheme 0
encodingStyles [ (pair scheme 0 style 1) (pair scheme 1 style 3) (pair scheme 2 style 0) … (pair scheme 5 style 0) ]
otherValues    [ (pair scheme 0 otherValue "") … ]
attribute 0  synSafe 1  outputEncodedLocals 0  useVerilogParameterRange 0  radix 2
)</pre>
<p><b>Cách đọc (giả thuyết, khớp mọi mẫu):</b> encoding có hiệu lực = <code>style</code> của
<code>(pair scheme S …)</code> với <code>S</code> = <code>scheme</code> của khối.''' + UNSURE + '''</p>
<table><tr><th><code>scheme</code></th><th><code>encodingStyles</code> (S:style)</th><th>Số machine trong mẫu</th>
<th>Code tool cũ sinh ra</th></tr>
<tr><td>0</td><td>0:0 1:1 2:0 3:0 4:0 5:0</td><td>19</td><td>sequential (mặc định)</td></tr>
<tr><td>3</td><td>0:0 1:1 2:0 3:0 4:0 5:0</td><td>5</td><td>sequential, <code>2'd0, 2'd1…</code></td></tr>
<tr><td>0</td><td>0:0 <b>1:3</b> 2:0 …</td><td>1 (bản gc_control_fsm cũ)</td><td>sequential, <code>5'd0…</code></td></tr>
<tr><td>0</td><td><b>0:1</b> 1:3 2:0 …</td><td>1 (gc_control_fsm sau khi đổi sang 1-Hot)</td>
<td>one-hot, <code>23'b…001, 23'b…010…</code></td></tr>
</table>
<table><tr><th>Giá trị <code>style</code></th><th>Ý nghĩa</th></tr>
<tr><td>0</td><td>mặc định, sinh sequential''' + UNSURE + '''</td></tr>
<tr><td>1</td><td><b>1-Hot</b>: đã xác minh 2026-11-09 (đổi trong tool cũ, chỉ <code>(pair scheme 0)</code> đổi
<code>style 0 → 1</code>)</td></tr>
<tr><td>3</td><td>chỉ gặp ở pair của scheme 1, không ảnh hưởng khi <code>scheme</code> = 0</td></tr>
</table>
<p>Cần xác minh thêm: <code>style</code> của Gray, Johnson, Manual (đổi lần lượt trong tool cũ, Save, diff); ý nghĩa
của số <code>scheme</code>, của <code>radix</code> (luôn 2, cả khi code sinh ra dùng <code>'d</code>) và của các cờ.</p>
<h3>2. Mã của từng state: <code>State encoding (Text … tm "SmEncodingMgr")</code></h3>
<p>Text ẩn. Khi encoding thủ công, mã của state nằm ở <code>st</code>. import_sm đọc vào
<code>State.encoding</code>.</p>
<h3>Trạng thái trong HDL Studio</h3>
<ul>
<li>Model: <code>Machine.encoding</code> ∈ <code>sequential, gray, onehot, johnson, manual</code>
(<code>src/model.py ENCODINGS</code>), sinh code ở <code>src/codegen/encoding.py</code>.</li>
<li><b>import_sm chưa đọc khối <code>Encoding</code></b>: mọi machine đọc từ .sm đều là <code>sequential</code>.</li>
<li><b>export_sm chưa ghi</b>: đổi encoding trong HDL Studio không được lưu vào .sm.</li>
</ul>
'''),
    ('signals', 'Bảng tín hiệu (Signals Table)', '''
<p>Mỗi tín hiệu là một <code>LeafLogPort</code> trong <code>model commonDM ldm</code>; thứ tự hiển thị là
<code>MRCItem litem &amp;N pos P</code> trong <code>pdm</code>. Nhóm là <code>LGroup</code>.</p>
<pre>*N (LeafLogPort
  port (LogicalPort lang 1 m 1 decl (Decl n "data_o" t "reg" b "[7:0]" o 3 eolc "comment"))
  uid 120,0  cat 8  scheme 1  expr "!rst_n"  defVal "0"  rstVal "0")</pre>
<table><tr><th>Khóa</th><th>Mã</th></tr>
<tr><td><code>LogicalPort m</code></td><td>không có = input, 1 output, 2 inout, 4 local</td></tr>
<tr><td><code>LeafLogPort scheme</code></td><td>không có = combinational, 1 clocked, 2 registered;
<code>ass "&lt;none&gt;"</code> = không gán</td></tr>
<tr><td><code>LeafLogPort cat</code></td><td>không có = Data; 1 Clock (Rising), 2 Clock (Falling), 3 Clock (Gated),
4 Clock (Specify), 8 Reset (Async Low), 9 Reset (Async High), 10 Reset (Async Specify), 11 Reset (Sync Low),
12 Reset (Sync High), 13 Reset (Sync Specify), 14 Enable (Low), 15 Enable (High), 16 Enable (Specify)
(<code>model.CATEGORY_CODES</code>)</td></tr>
</table>
<p>Đọc: import_sm <code>_signals</code>. Ghi: export_sm <code>_signal_table</code> và các hàm đi kèm (thêm, xóa,
đổi tên, đổi thứ tự).</p>
'''),
    ('transitions', 'Transition', '''
<pre>(Transition uid …  shape (Spline pts ["x,y" …] arrow 1)
  start &amp;5  end &amp;9
  tb (TransitionBlock shape (Rectangle) condition (MLText st "a &amp; b")
                      actions (MLText st "x &lt;= 1;") lineShape (Line))
  tp (TransitionPriority shape (Circle) pr (Text st "1")))</pre>
<p><code>start</code>/<code>end</code> trỏ tới State, Junction, Link, point hoặc EntryPoint/ExitPoint. Đi qua
hierarchical state: import_sm nối các đoạn qua entry/exit point thành đường đi phẳng khi sinh code. Action
<code>"&lt; Automatic &gt;"</code> = không có action.</p>
'''),
    ('symbol', 'Port của symbol (.sb)', '''
<p>Một port của unit xuất hiện ba lần trong <code>symbol.sb</code>:</p>
<ol>
<li>Bảng port: <code>LogPort port (LogicalPort lang m decl (Decl n t b o suid))</code> trong
<code>commonDM ldm</code>, và một hàng <code>MRCItem litem &amp;N pos P</code> trong sheet.</li>
<li>Port vẽ trên thân: <code>CptPort</code> trong <code>SymbolBody optionalChildren</code>, gồm text tên
(<code>CPTG f "name"</code> hoặc <code>"name : [7:0]"</code>), text khai báo (<code>dt</code>:
<code>"input  wire  name;"</code>) và bản sao <code>thePort</code>.</li>
<li>Thứ tự <code>Decl o</code>: input trước, rồi output, rồi inout, mỗi nhóm theo tên. Text khai báo đặt ở
y = 3200 + 800 × o.</li>
</ol>
<p>Vị trí: input ở cạnh trái, output/inout ở cạnh phải, cách nhau 1000, port đầu cách đỉnh 1000. Khi lưu một .sm
có port thay đổi, export_sb (<code>sync_symbol_ports</code>) sửa symbol.sb theo quy tắc này.</p>
'''),
    ('bd', 'Block diagram (.bd)', '''
<p>Diagram là các object trong <code>model optionalChildren</code>; dây (<code>Wire</code>) nối chúng bằng tham chiếu.</p>
<table><tr><th>Trên diagram</th><th>Trong file</th><th>import_bd đọc thành</th></tr>
<tr><td>Component</td><td><code>SaComponent</code>; tên instance, thư viện, unit, tham số lấy từ
<code>Header instances</code> (khớp qua <code>uid</code>), nếu không có thì từ các text <code>ttg</code></td>
<td><code>BdInstance</code></td></tr>
<tr><td>Cổng ModuleWare</td><td><code>MWC</code></td><td><code>BdInstance</code>, thư viện <code>moduleware</code></td></tr>
<tr><td>Pin</td><td><code>CptPort</code> trong component: <code>thePort (LogicalPort m decl (Decl n b o))</code>; cạnh = cạnh
gần tâm nhất; hướng = <code>Triangle ro</code> (0 lên, 90 phải, 180 xuống, 270 trái); có <code>FFT</code> = pin clock</td>
<td><code>BdPin</code></td></tr>
<tr><td>Dây</td><td><code>Wire on &amp;Net start &amp;N end &amp;N</code>, điểm ở <code>shape pts</code>, slice ở
<code>sl</code>, nhãn tên là Text <code>tm "WireNameMgr"</code></td><td><code>BdWire</code></td></tr>
<tr><td>Net</td><td><code>Net decl (Decl n …)</code> và một <code>LeafLogPort</code> trong bảng net</td>
<td>tên net, <code>Signal</code></td></tr>
<tr><td>Port của module</td><td><code>PortIoIn</code> / <code>PortIoOut</code> / <code>PortIoInOut</code></td>
<td><code>BdPortIo</code></td></tr>
<tr><td>Embedded block</td><td><code>HdlText</code> + <code>EmbeddedText commentText</code>; tên/số ở
<code>Header embeddedInstances</code> theo cùng thứ tự</td><td><code>BdEmbedded</code></td></tr>
<tr><td>Generate frame</td><td><code>Frame</code>: không có style = FOR, 1 = IF, 2 = ELSE</td><td><code>BdFrame</code></td></tr>
<tr><td>Chấm nối</td><td><code>BdJunction</code></td><td><code>BdJunction</code></td></tr>
<tr><td>Title block</td><td><code>CommentText titleBlock 1</code>, nhóm bằng <code>Grouping</code></td><td><code>BdComment</code></td></tr>
</table>
<p>Đầu dây được đổi thành chuỗi gắn: <code>pin:&lt;inst&gt;:&lt;pin&gt;</code>, <code>pio:&lt;id&gt;</code>,
<code>emb:&lt;id&gt;</code>, <code>jct:&lt;id&gt;</code>. Object dưới <code>model default*</code> là template,
không phải nội dung diagram.</p>
<p><b>Chưa có export_bd</b>: HDL Studio chưa ghi lại .bd. Block diagram sửa trong HDL Studio được lưu thành
<code>struct.bd.json</code>.</p>
'''),
    ('coverage', 'Độ phủ: khóa chưa implement', '''
<p>Kiểm tra ngày 2026-11-09 trên 26 .sm, 93 .sb, 67 .bd mẫu. Chỉ liệt kê khóa có ý nghĩa với thiết kế; hình vẽ,
font, màu, thiết lập in, lưới, biến môi trường và template được giữ nguyên khi ghi .sm nên không tính.
<b>Đ</b> = import đọc, <b>G</b> = export ghi lại khi sửa trong HDL Studio.</p>
<table><tr><th>#</th><th>File</th><th>Khóa</th><th>Đ</th><th>G</th><th>Trong mẫu</th><th>Hậu quả</th></tr>
<tr><td>1</td><td>.sm</td><td><code>ConcurrentSM encoding (Encoding …)</code></td><td>✗</td><td>✗</td><td>26 machine, 1 one-hot</td>
<td><b>Code sai</b>: machine 1-Hot sinh ra sequential. Đổi encoding trong HDL Studio không lưu được.</td></tr>
<tr><td>2</td><td>.sm</td><td><code>State encoding</code> (mã thủ công)</td><td>✓</td><td>✗</td><td>chưa dùng</td>
<td>Mã state sửa trong HDL Studio mất khi lưu .sm.</td></tr>
<tr><td>3</td><td>.sm</td><td><code>SmGenChar nextStateClocking</code></td><td>✓</td><td>✗</td><td>0 ở mọi mẫu</td>
<td>Đổi trong HDL Studio không lưu được.</td></tr>
<tr><td>4</td><td>.sm</td><td><code>State isWait</code>, <code>wait</code> của state đã có</td><td>✓</td><td>✗</td><td>—</td>
<td>Chỉ state mới được ghi wait; đổi wait của state cũ không lưu.</td></tr>
<tr><td>5</td><td>.sm</td><td>Bảng tham số <code>LogGeneric</code></td><td>✓</td><td>✗</td><td>có</td>
<td>Thêm / sửa / xóa tham số không lưu vào .sm (export_sm báo warning).</td></tr>
<tr><td>6</td><td>.sm .sb .bd</td><td><code>GiElement e</code> (comment tham số)</td><td>✗</td><td>✗</td><td>156 tham số</td>
<td><code>Parameter.comment</code> luôn rỗng; mất khi lưu JSON.</td></tr>
<tr><td>7</td><td>.sm</td><td><code>SmGenChar casePragma</code></td><td>✗</td><td>✗</td><td>1 ×6, 2 ×3</td>
<td>Chưa rõ ý nghĩa: code tool cũ sinh ra không có pragma nào (gc_control_fsm có 2).''' + UNSURE + '''</td></tr>
<tr><td>8</td><td>.sm</td><td>Kiểu khai báo state (<code>Machine.state_decl</code>: parameter / localparam / enum)</td><td>✗</td><td>✗</td>
<td>parameter ở mọi mẫu</td><td>Chưa biết tool cũ lưu ở khóa nào.''' + UNSURE + '''</td></tr>
<tr><td>9</td><td>.sb .bd</td><td><code>Decl prec</code> (comment trước khai báo port, vd. <code>"// Slave Side"</code>)</td>
<td>✗</td><td>✗</td><td>.sb 12, .bd 1</td><td>Comment nhóm port mất; có thể khác code tool cũ sinh ra.</td></tr>
<tr><td>10</td><td>.sm .bd</td><td><code>CommentText</code> tự do (không phải title block)</td><td>✗</td><td>—</td><td>.sm 27, .bd 47</td>
<td>Không hiện trên diagram; mất khi lưu .bd thành JSON. .sm vẫn giữ trong file.</td></tr>
<tr><td>11</td><td>.bd</td><td>Toàn bộ file (chưa có export_bd)</td><td>✓</td><td>✗</td><td>67 file</td>
<td>Chế độ “dùng luôn định dạng tool cũ” chưa có cho block diagram.</td></tr>
<tr><td>12</td><td>.bd</td><td><code>MWC prms</code>, <code>Instance mwi</code></td><td>✗</td><td>✗</td><td>1</td>
<td>Tham số của cổng ModuleWare không đọc.</td></tr>
<tr><td>13</td><td>.sm</td><td><code>SmResetPoint level / mode</code>, <code>SmEnablePoint level</code></td><td>✗</td><td>✗</td><td>1 / 2</td>
<td>Codegen lấy mức tích cực từ <code>cat</code> trong bảng tín hiệu; chỉ ảnh hưởng nếu hai nơi khác nhau.''' + UNSURE + '''</td></tr>
<tr><td>14</td><td>.sm .bd</td><td><code>DocumentHdr includeRefs</code></td><td>✗</td><td>✗</td><td>.sm 20, .bd 65</td>
<td>Danh sách suy ra từ Compiler Directives (đã đọc/ghi). Sửa directives không cập nhật danh sách này.''' + UNSURE + '''</td></tr>
<tr><td>15</td><td>.sm</td><td><code>StateDiagram viewArea</code></td><td>✓</td><td>✗</td><td>có</td><td>Chỉ là vùng đang xem.</td></tr>
</table>
<p>Không cần implement (không có nội dung trong mẫu hoặc chỉ là template): <code>State useCase / caseExpr</code>
(useCase không bao giờ bật), action của reset point (luôn <code>"&lt; Automatic &gt;"</code>), <code>Frame decls</code>
(chỉ có tiêu đề), <code>SmLocalDecl</code> / <code>SmProcessDecl</code> (rỗng), <code>SymDeclBlock</code> (rỗng),
<code>Ripper</code>, <code>Bundle</code>, <code>Protocol</code>, <code>GlobalConnector</code>, <code>PortMapFrame</code>,
<code>Blk</code>, <code>VhdlComponent</code>, <code>VerilogComponent</code>, các <code>PortIo</code> buffer / slave / master
(chỉ có trong <code>default*</code>).</p>
'''),
    ('code', 'HDL Studio đọc / ghi gì', '''
<table><tr><th>Module</th><th>Việc</th></tr>
<tr><td><code>formats/sexpr.py</code></td><td>Đọc/ghi cú pháp; ghi lại không đổi = giống từng byte</td></tr>
<tr><td><code>formats/import_sm.py</code></td><td>.sm → <code>FsmView</code>: tín hiệu, tham số, các khối text,
machine, state, junction, link, point, transition (kèm hình học)</td></tr>
<tr><td><code>formats/export_sm.py</code></td><td>Đọc lại .sm gốc, chỉ sửa phần đã thay đổi, tạo object mới từ template
<code>default*</code></td></tr>
<tr><td><code>formats/export_sb.py</code></td><td>Đồng bộ port của symbol.sb theo bảng tín hiệu</td></tr>
<tr><td><code>formats/sheet.py</code></td><td>Bố cục bảng (Sheet, MRCItem, cột)</td></tr>
<tr><td><code>formats/import_bd.py</code></td><td>.bd → <code>BlockDiagram</code> (chỉ đọc; chưa có export_bd), và
hình dạng/port của symbol khi đặt instance mới (<code>symbol_geometry</code>)</td></tr>
</table>
<p>Cột <b>Code</b> trong bảng khóa liệt kê những dòng trong <code>src/formats</code>, <code>src/project</code>,
<code>src/model.py</code> có chuỗi <code>'tên khóa'</code>. Đây là khớp theo tên, nên một khóa phổ biến
(<code>name</code>, <code>shape</code>) có thể khớp với kiểu khác.</p>
<h3>Cập nhật trang này</h3>
<pre>python resources/scripts/format_ref.py            # mẫu: $HDLSTUDIO_SAMPLES (mặc định D:/workspace)</pre>
<p>Ý nghĩa viết tay nằm trong <code>resources/scripts/format_notes.py</code>, giao diện trong
<code>format_ref.html</code>. Sau khi sửa import/export hoặc tìm ra ý nghĩa một khóa: sửa notes, thêm một dòng vào
lịch sử, chạy lại script và commit trang cùng với code.</p>
<p>Để không đưa nội dung thiết kế vào tài liệu, chuỗi trong ngoặc kép được che thành <code>"…"</code> khi: là giá trị
của khóa mang nội dung thiết kế (tên, thư viện, unit, range, biểu thức, giá trị, comment — <code>DESIGN_KEYS</code>);
trông giống đường dẫn, <code>`include</code> hoặc tên file HDL; hoặc xuất hiện ở ít hơn 3 file mẫu hay ít hơn 40% số
file cùng loại.</p>
'''),
]

# -- change log -----------------------------------------------------------------------------
CHANGES = [
    ('2026-11-09', 'Trang đầu tiên: cú pháp, cấu trúc .sm/.sb, bảng tín hiệu, port của symbol. Xác minh '
                   '<code>Encoding encodingStyles (pair scheme 0 style 1)</code> = 1-Hot (gc_control_fsm). '
                   'Ghi nhận import_sm/export_sm chưa đọc/ghi encoding của machine. 5 mẫu dùng '
                   '<code>scheme 3</code> và sinh sequential: encoding có hiệu lực có lẽ là style của pair '
                   'cùng số scheme.'),
    ('2026-11-09', 'Thêm block diagram <code>.bd</code>: kiểu object, chủ đề Block diagram, cấu trúc file.'),
    ('2026-11-09', 'Thêm chủ đề <a href="#topic-coverage">Độ phủ</a>: 15 khóa chưa đọc hoặc chưa ghi.'),
]
