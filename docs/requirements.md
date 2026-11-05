# Đặc tả yêu cầu – Vietsemi HDL Studio

| | |
|---|---|
| Phiên bản | 0.9 (cập nhật theo bản cài đặt: tên sản phẩm, Python/PySide6, chạy trên Windows) |
| Ngày | 2026-11-05 |
| Tham chiếu | Tài liệu người dùng của một tool thương mại tương tự (chỉ dùng để tham khảo tính năng, không sao chép nội dung) |
| Trạng thái | Chờ người dùng duyệt và bổ sung yêu cầu chức năng chi tiết |

Mức ưu tiên: **P1** = MVP, bắt buộc có ở bản đầu; **P2** = bản tiếp theo; **P3** = có thể làm sau.

---

## 1. Mục tiêu và phạm vi

### 1.1 Mục tiêu
Tool có **3 chức năng chính**:
1. **Quản lý HDL design**: project, library, design unit, cây phân cấp.
2. **Sinh code (generate)**: từ các view đồ họa và template sinh ra Verilog/SystemVerilog.
3. **Bảo trì code (maintain)**: soạn, sửa, import, trực quan hóa và quản lý phiên bản source HDL.

Dữ liệu design được lưu dưới dạng **file source Verilog/SystemVerilog**. Người dùng tạo và sửa design bằng text editor hoặc graphical editor.

### 1.2 Trong phạm vi
- Ngôn ngữ: Verilog (IEEE 1364-2005) và SystemVerilog (IEEE 1800-2017).
- Hệ điều hành: CentOS Stream 9 (ưu tiên), sau đó CentOS 7 và CentOS 10. Tool cũng chạy trên Windows (máy có HDS 2021.1, dùng để đối chiếu với HDS).

### 1.3 Ngoài phạm vi (ít nhất ở giai đoạn đầu)
| Hạng mục | Lý do |
|---|---|
| VHDL | Người dùng chỉ cần Verilog/SV |
| Tích hợp simulator và synthesis (Questa, VCS, Vivado, Quartus, …) | Không thuộc 3 chức năng chính. Có thể làm sau bằng cơ chế "task" chạy script ngoài (xem TSK-1) |
| Register generator, trợ lý UVM, requirements tracing | Không thuộc 3 chức năng chính |
| Lint hoặc kiểm tra quy tắc coding (kiểu DesignChecker) | P3, cân nhắc sau |
| In ấn và xuất tài liệu HTML | P3 |
| OLE | Không cần |

---

## 2. Khái niệm và mô hình dữ liệu

| Khái niệm | Định nghĩa |
|---|---|
| **Project** | File cấu hình (dạng text, thân thiện với Git) chứa danh sách library và thiết lập. Có 2 tầng: **user project** của từng người và **shared project** dùng chung cho cả nhóm |
| **Library** | Tên logic, ánh xạ tới các thư mục vật lý: **HDL dir** (source `.v`/`.sv`) và **meta dir** (file đồ họa và dữ liệu phụ) |
| **Loại library** | **Regular**: sửa được, generate được. **Protected**: chỉ đọc (IP đã chốt, thư viện chuẩn) |
| **Design unit** | Một `module`, `interface`, `package` hoặc `program` trong một library |
| **View** | Một cách mô tả design unit: *Text view* (file HDL), *Block diagram*, *State machine*, … Một design unit có thể có nhiều view, trong đó 1 view là **default view** |
| **Interface / Symbol** | Danh sách port và parameter của design unit, dùng chung cho mọi view |
| **Side data** | File liên quan khác: constraint, script, tài liệu, … |

**Nguyên tắc lưu trữ (đã chốt 2026-10-30):**
- File HDL là **nguồn gốc (source of truth)** của text view.
- View đồ họa lưu trong meta dir dưới dạng text (JSON/YAML), và **sinh ra** file HDL nằm trong HDL dir.
- Với design unit có view đồ họa, file HDL sinh ra là sản phẩm phụ: muốn sửa logic thì sửa view đồ họa rồi generate lại (xem GEN-8).
- Mọi file cấu hình đều là text để dùng tốt với Git.

### 2.1 Định dạng project `.hdp` (tương thích với tool đang dùng)
Rút ra từ file mẫu `dti_hbm.hdp`. Đây là file dạng INI, mỗi section là một bảng `tên_library = giá_trị`:

| Section | Ý nghĩa | Ví dụ |
|---|---|---|
| `[hdl]` | Thư mục HDL của library. **Một library có thể có nhiều dòng**, tức nhiều thư mục HDL | `dti_io = $HDS_PROJECT_DIR/libs/dti_io` và `dti_io = …/dti_io/hdl/base_verilog` |
| `[hds]` | Thư mục dữ liệu đồ họa (meta dir) | `datapath = $HDS_PROJECT_DIR/libs/datapath/hds` |
| `[hds_settings]` | `default_library`, `design_root` (top design: library, unit, view), `version` | `default_library = dti_hbm` |
| `[includes_search_path]` | Include path cho từng library. Giá trị có thể là biến môi trường | `dti_axi_sw = $dti_axi_sw` |
| `[library_files_inclusion]` | Chế độ library: `all` hoặc chỉ các file được chỉ định | `datapath = all` |
| `[library_type]` | `regular` (sửa được) hoặc `standard` (hiện là **Protected**, chỉ đọc) | `ddr_bist = standard` |
| `[protected_library_traversal]` | Có duyệt phân cấp vào bên trong library protected hay không (`standard`/`no`) | `dti_umc40_phy_lib = no` |
| `[shared]` | Đường dẫn tới shared project | `others = $HDS_TEAM_HOME/shared.hdp` |

Biến đường dẫn: `$HDS_PROJECT_DIR` là thư mục chứa file `.hdp`. `$HDS_TEAM_HOME` và các biến khác lấy từ môi trường.

---

## 3. Yêu cầu chức năng

### 3.1 Project và library (PRJ)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| PRJ-1 | Tạo project mới qua wizard: tên, mô tả, thư mục, default library | P1 |
| PRJ-2 | Mở, đóng project và nhớ danh sách project gần đây | P1 |
| PRJ-3 | Hỗ trợ user project và shared project. User project có thể ghi đè ánh xạ của shared project | P2 |
| PRJ-4 | Tạo, sửa, xóa library: tên logic, HDL dir, meta dir, loại Regular/Protected | P1 |
| PRJ-5 | Đường dẫn trong ánh xạ có thể chứa biến môi trường (`$PROJ_ROOT/rtl`) để project dùng được ở nhiều vị trí | P1 |
| PRJ-6 | Chế độ library: *gồm mọi file trong HDL dir* hoặc *chỉ các file được chỉ định* | P1 |
| PRJ-7 | Thiết lập theo library: macro `` `define ``, include search path, phiên bản ngôn ngữ mặc định | P1 |
| PRJ-8 | Refresh library để phát hiện file thêm, xóa, sửa từ bên ngoài, có thể tự động qua file watcher | P1 |
| PRJ-9 | Copy library sang project khác | P3 |
| PRJ-10 | **Mở trực tiếp file `.hdp`** có sẵn (định dạng ở mục 2.1) và hiển thị đúng danh sách library, loại library, include path, shared project | P1 |
| PRJ-11 | Một library có thể ánh xạ tới **nhiều thư mục HDL** | P1 |
| PRJ-12 | Ghi lại file `.hdp` khi sửa project, giữ nguyên thứ tự và các section/khóa mà tool không hiểu | P2 |
| PRJ-13 | Đọc shared project (`shared.hdp`) được tham chiếu trong `[shared]`. Library của shared project hiển thị riêng | P1 |
| PRJ-14 | Tôn trọng `[protected_library_traversal]`: không mở rộng phân cấp vào library protected khi giá trị là `no` | P2 |
| PRJ-15 | Hiển thị lỗi rõ ràng khi biến môi trường trong đường dẫn chưa được đặt hoặc thư mục không tồn tại | P1 |
| PRJ-16 | **Khóa chỉnh sửa nhiều người dùng**: khi mở một view để sửa thì tạo file `<view>.<ext>.lck` (user, group, host, PID, thời gian), **tương thích với file khóa của tool cũ**. Nếu view đang bị người khác khóa thì chỉ mở chế độ chỉ đọc và cho biết ai đang khóa | P1 |
| PRJ-17 | Phát hiện khóa "mồ côi" (tiến trình không còn chạy trên host đó) và cho phép gỡ khóa sau khi xác nhận | P2 |

### 3.2 Import design có sẵn (IMP)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| IMP-1 | Wizard "Add existing design" có 2 lựa chọn: **trỏ tới** file tại chỗ, hoặc **copy** vào project | P1 |
| IMP-2 | Import từ thư mục (quét đệ quy, lọc theo phần mở rộng) | P1 |
| IMP-3 | Import từ filelist (`.f`) hỗ trợ `-f`, `+incdir+`, `+define+`, `-v`, `-y`, `+libext+` | P1 |
| IMP-4 | Phân tích design để đề xuất ánh xạ library | P2 |
| IMP-5 | **Reference file**: tham chiếu tới file nằm ngoài HDL dir mà không copy | P2 |
| IMP-6 | Báo cáo các file không parse được, kèm vị trí lỗi | P1 |
| IMP-7 | **Import view đồ họa của tool cũ** từ `hds/<unit>/`: `.sm` (state machine), `.bd` (block diagram), `.sb` (symbol). Định dạng ghi trong [hds-file-format.md](hds-file-format.md) | P1 |
| IMP-8 | Khi import, bỏ qua các biến lưu sẵn (`VExpander`) như đường dẫn tuyệt đối, user, host | P1 |
| IMP-9 | Import giữ nguyên vị trí và kích thước đối tượng để sơ đồ trông giống bản gốc | P2 |
| IMP-10 | Kiểm tra sau import: code do tool mới sinh ra từ view đã import phải **tương đương về chức năng** với file `.v` mà tool cũ đã sinh | P1 |
| IMP-11 | Đọc được file `.hdp` riêng của từng library (ví dụ `libs/protocol_controller/protocol_controller.hdp`) | P2 |
| IMP-12 | Bỏ qua các thư mục và file nội bộ của tool cũ: `.hdlsidedata/`, `.xrf/`, `.cache.dat` | P1 |

### 3.3a Cửa sổ chính – Design Manager (UI)
Bố cục tham khảo từ ảnh chụp tool đang dùng:

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| UI-1 | Thanh tiêu đề hiển thị tên project đang mở | P1 |
| UI-2 | Menu chính: File, Edit, View, HDL, Tasks, Tools, Options, Window, Help, và một toolbar | P1 |
| UI-3 | **Thanh lối tắt bên trái** đổi theo ngữ cảnh. Ở tab Project: New Project, Open Project, New Library, Edit Mappings, Set As Default, Explore Library, New/Add, Version Management, Close Project | P1 |
| UI-4 | **Tab Project**: dòng đầu là đường dẫn *My Project* (file `.hdp`), Verilog Library Search Path, Implicit Include Libraries, *Shared Project*. Bên dưới là library chia nhóm **Regular / Protected / Downstream Only**, mỗi nhóm có ô check để hiện hoặc ẩn và có số lượng `[15 items]` | P1 |
| UI-5 | Icon phân biệt library của user và library của shared project. **Default library** có dấu riêng | P1 |
| UI-6 | Mở library (double-click hoặc Explore Library) thì tạo một **tab Design Explorer** mới ở dưới. Tab đầu tiên luôn là "Project" | P1 |
| UI-7 | Thanh trạng thái ở cuối cửa sổ | P1 |
| UI-8 | Panel bên phải có thể ẩn hiện (tương đương Launch Pad / Sub Browser / Tasks-Templates) | P3 |

### 3.3 Design Explorer (EXP)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| EXP-1 | Cửa sổ chính có cây project/library ở bên trái và Design Explorer ở giữa | P1 |
| EXP-2 | Chế độ **Design Units**: library → design unit → các view, kèm icon theo loại | P1 |
| EXP-3 | Chế độ **Files**: cây thư mục vật lý | P1 |
| EXP-4 | Chế độ **Hierarchy**: cây instance bắt đầu từ một top được chọn. Có thể đánh dấu top-level | P1 |
| EXP-5 | Đánh dấu **component chưa bind**, tức module được instantiate nhưng không tìm thấy định nghĩa | P1 |
| EXP-6 | Tìm kiếm nhanh, lọc và nhóm theo tên, loại, trạng thái | P1 |
| EXP-7 | Cột cấu hình được: tên, loại, file, ngày sửa, trạng thái generate, trạng thái Git | P2 |
| EXP-8 | **Báo cáo tham chiếu**: module X được instantiate ở đâu (where-used) | P1 |
| EXP-9 | Xóa design unit: chỉ gỡ khỏi project, hoặc xóa khỏi đĩa (có xác nhận). Hỗ trợ xóa theo phân cấp | P2 |
| EXP-10 | Đổi tên design unit và cập nhật mọi chỗ instantiate | P2 |
| EXP-11 | Lưu và khôi phục bố cục cửa sổ, cột, bộ lọc ("viewpoint") | P3 |
| EXP-12 | Cửa sổ Log: console, kết quả từng task, thông báo lỗi có thể click để nhảy tới file:dòng | P1 |
| EXP-13 | Design Explorer của một library chia **3 khung** cùng lúc: *Design Units* (trên trái), *Files* (dưới trái), *Design Hierarchy* (phải) | P1 |
| EXP-14 | Cột của khung Design Units: **Design Unit, Type, Extends, Language, Time Stamp**. *Language* là `Verilog 2005` hoặc `SystemVerilog`. *Type* theo user guide: **Component** (interface cố định, có symbol, dùng lại được), **Block** (interface động, xác định bởi các tín hiệu nối vào nó trên sơ đồ cha), **Module** (chỉ có HDL text) và *unknown* | P1 |
| EXP-19 | Đánh dấu trên icon: top-level design unit, default view, design root, đối tượng có lỗi parse, library chỉ gồm file được chỉ định, view chỉ đọc | P1 |
| EXP-15 | Cột của khung Files: **Files, Type, Extends, Size, Time Stamp**. Có các nhóm: *Design Files* và *Documentation & Visualization* | P1 |
| EXP-16 | Cột của khung Design Hierarchy: **Design Hierarchy** (tên instance), **Design Unit Name**, **Extends**, **Name**. Hiển thị cả **khối generate** (ví dụ `FOR : ps_chan_num`) như một cấp trong cây | P1 |
| EXP-17 | Tên library hoặc unit có lỗi parse thì hiện **màu đỏ** kèm số file lỗi, ví dụ `protocol_controller [1 file not parsed]` | P1 |
| EXP-18 | Thanh lối tắt bên trái ở chế độ Explore: **New/Add, Check** (P3), Document & Visualize (P3). Simulate, Synthesize, Registers, SVAssistant nằm ngoài phạm vi | P1 |

### 3.4 Tạo design content và template (NEW / TPL)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| NEW-1 | Wizard "New design content", bước 1: chọn loại (Verilog module, SV module, SV interface, SV package, include file, Block diagram, State machine, text file) | P1 |
| NEW-2 | Wizard bước 2: khai báo **interface** bằng bảng port (tên, hướng, kiểu, range) và parameter. Gõ `data[7:0]` thì range tự tách sang cột riêng | P1 |
| NEW-3 | Tạo view mới cho một design unit hoặc block có sẵn ("open down" từ sơ đồ khối) | P2 |
| TPL-1 | Template HDL có biến thay thế: `%(library)`, `%(unit)`, `%(view)`, `%(user)`, `%(host)`, `%(date)`, `%(time)`, `%(version)`, `%(moduleBody)` | P1 |
| TPL-2 | Template Manager để xem, sửa, tạo template. Có template **team** (dùng chung) và template **user** (cá nhân) | P2 |
| TPL-3 | Header mặc định của file sinh ra cấu hình được theo từng loại view | P1 |
| TPL-4 | Cập nhật interface của text view: khi sửa port trong bảng, phần khai báo module trong file được cập nhật mà không động vào thân module | P2 |

### 3.5 Sinh code (GEN)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| GEN-1 | Generate HDL từ view đồ họa cho 1 view, 1 design unit, hoặc **cả cây phân cấp** | P1 |
| GEN-2 | Mặc định chỉ generate khi view đồ họa mới hơn file HDL (out-of-date). Có tùy chọn "always regenerate" | P1 |
| GEN-3 | Quy tắc đặt tên file sinh ra cấu hình được, ví dụ `%(unit).%(ext)` hoặc `%(unit)_%(view).%(ext)` | P1 |
| GEN-4 | Tùy chọn phong cách code: độ rộng tab, `begin`/`else` xuống dòng, dòng trống quanh comment, nhãn cho khối `always` (tiền tố, hậu tố, hoa/thường), pragma tổng hợp | P1 |
| GEN-5 | Tùy chọn SV: dùng `logic`, `always_ff`/`always_comb`, kiểu port ANSI | P1 |
| GEN-6 | Header file sinh ra lấy từ template (TPL-3). Có thể kèm thông tin generate (tool, thời điểm) | P1 |
| GEN-7 | Xem nhanh HDL đã sinh ra từ một view đồ họa ("View generated HDL") | P1 |
| GEN-8 | Đánh dấu file sinh ra (comment đầu file) để cảnh báo người dùng không sửa tay. Phát hiện khi file sinh ra bị sửa tay và hỏi lại người dùng trước khi ghi đè | P1 |
| GEN-9 | Chạy generate từ **dòng lệnh** (batch mode, không cần GUI) để dùng trong CI/Makefile | P2 |
| GEN-10 | **Chọn ngôn ngữ đích khi sinh code: Verilog-2005 hoặc SystemVerilog-2017.** Mặc định của project là **SystemVerilog**. Mỗi view đồ họa có thể ghi đè. Tool cũ chỉ sinh được Verilog từ view đồ họa | P1 |
| GEN-11 | **Chế độ Verilog** sinh code giống hệt tool cũ (bố cục, tên khối, căn cột, thứ tự port), theo [codegen-reference.md](codegen-reference.md) mục 1–3 | P1 |
| GEN-12 | **Chế độ SystemVerilog** theo bảng ánh xạ ở [codegen-reference.md](codegen-reference.md) mục 4: `logic`, `always_comb`, `always_ff`, state dạng `typedef enum`, đuôi file `.sv`. Bố cục giữ như bản Verilog | P1 |
| GEN-13 | Tùy chọn SystemVerilog: `case`, `unique case` hoặc `priority case`; clocked output bằng `assign` hoặc `always_comb`; gán port instance đầy đủ, `.port` hoặc `.*` | P2 |
| GEN-19 | **Kiểu khai báo state do người dùng chọn**: `parameter`, `localparam` hoặc `enum` (`typedef enum logic [N-1:0] {…} <machine>_state_t`). `enum` chỉ dùng được khi ngôn ngữ đích là SystemVerilog; ở chế độ Verilog ô chọn này bị khóa. Đặt được ở mức project (preference) và ghi đè cho từng máy trạng thái. Giá trị mã hóa (FSMG-4) luôn được ghi tường minh trong cả ba kiểu. Mặc định là `parameter`, giống tool cũ | P1 |
| GEN-14 | Kiểm tra trước khi sinh SystemVerilog: mỗi biến chỉ được gán trong một khối `always_comb`/`always_ff`. Vi phạm thì báo lỗi kèm vị trí trên sơ đồ | P1 |
| GEN-15 | Code người dùng (action, embedded block, declarations, concurrent statements) được **chép nguyên văn** ở cả hai chế độ. Kiểm tra cú pháp theo ngôn ngữ đích | P1 |
| GEN-16 | Block diagram ở chế độ SystemVerilog instantiate được component có port kiểu SV (`interface`/`modport`, `struct`, `enum`, mảng nhiều chiều) **mà không ép về kiểu Verilog-95** như tool cũ | P2 |
| GEN-17 | Kiểm tra hồi quy: (a) chế độ Verilog cho ra kết quả giống các file golden của tool cũ, bỏ qua header; (b) chế độ SystemVerilog parse được bằng slang, lint sạch bằng Verilator, và **tương đương chức năng** với bản Verilog | P1 |
| GEN-18 | Khi đổi ngôn ngữ đích của một view: đổi đuôi file, xóa file cũ (sau khi xác nhận) và cập nhật thông tin trong library | P2 |

### 3.6 Bảo trì code: text editor (TXT)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| TXT-1 | Editor tích hợp có tô màu cú pháp Verilog/SV, số dòng, tìm/thay thế (có regex), undo/redo | P1 |
| TXT-2 | Chọn phiên bản ngôn ngữ cho từng file: Verilog-1995, Verilog-2005, SystemVerilog | P1 |
| TXT-3 | Báo lỗi cú pháp ngay trong editor, có gạch chân và danh sách lỗi | P1 |
| TXT-4 | Điều hướng code: nhảy tới định nghĩa module hoặc tín hiệu, outline các khối trong file | P2 |
| TXT-5 | Cho phép cấu hình **editor ngoài** (gvim, emacs, gedit, VS Code) thay cho editor tích hợp | P1 |
| TXT-6 | Gợi ý, tự hoàn thành tên port, tín hiệu, module. Chèn nhanh khung instantiate của một module | P2 |
| TXT-7 | So sánh 2 file hoặc 2 phiên bản (diff) | P2 |

### 3.7 Graphical editor (GFX)
Chi tiết sẽ được bổ sung khi có ảnh chụp màn hình và tài liệu của các graphical editor.

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| GFX-1 | **Block diagram editor**: block/component, port, net, bus, bus ripper, nhãn net, generic/parameter, sinh ra HDL structural | P1 |
| GFX-2 | **State machine editor**: state, transition, điều kiện, action, reset, kiểu mã hóa, sinh ra HDL FSM | P1 |
| GFX-3 | **Symbol editor**: hình khối và vị trí port của design unit | P2 |
| GFX-4 | IBD (bảng kết nối dạng ma trận), Flow chart, Truth table | P3 |
| GFX-5 | Tự động sắp xếp layout và đi dây | P2 |

### 3.7.1 State Machine editor (FSM) – chi tiết
Rút ra từ view `protocol_controller/gc_control_fsm/fsm` của project mẫu. Một design unit (ví dụ `gc_control_fsm`) có thể chứa **nhiều máy trạng thái chạy song song** (*Concurrent Machines*, ví dụ `dram_control_fsm`).

**Khung cửa sổ**
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FSM-1 | Tiêu đề: `Project <prj>: <library>/<unit>/<view> [<machine>] (State Diagram)` | P1 |
| FSM-2 | Menu: File, Edit, View, HDL, Diagram, Tasks, Add, Options, Window, Help. Simulate và Animation nằm ngoài phạm vi | P1 |
| FSM-3 | **Structure Navigator** bên phải, dạng cây: *Signals Table*, *Parameters Table*, tên unit → *Declarations/Statements* (Compiler Directives, Module Declarations, Concurrent Statements, Signal Status) → *Concurrent Machines* → từng máy. Click vào nút nào thì nhảy tới phần đó | P1 |
| FSM-4 | Khung **Content** dưới Navigator: liệt kê đối tượng theo loại (state, link, junction, …) kèm số lượng, mở rộng để chọn từng đối tượng | P2 |
| FSM-5 | Canvas có lưới chấm, khung trang (page boundary), zoom/pan, nhiều trang | P1 |

**Đối tượng trên sơ đồ**
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FSM-10 | **State**: hình tròn có tên. Có **state action** gắn kèm (khung chứa các câu gán) | P1 |
| FSM-11 | **Transition**: mũi tên giữa 2 state, có khung **condition** (phía trên) và **transition action** (phía dưới đường kẻ) | P1 |
| FSM-12 | **Priority**: nhiều transition kiểu IF rời một state được đánh số ưu tiên (1, 2, 3, …), xét theo thứ tự đó. Transition có điều kiện `OTHERS` luôn được xét cuối | P1 |
| FSM-13 | **Junction**: gom nhiều transition thành các transition từng phần. Junction kiểu case có `CASE: <biểu_thức>`, mỗi nhánh là một giá trị. **Transition order** của nhánh case có ý nghĩa trong Verilog vì nhánh khớp đầu tiên được chọn | P1 |
| FSM-14 | **Link**: cờ màu vàng mang tên state đích (ví dụ `ST_RUN`), thay cho một mũi tên dài | P1 |
| FSM-15 | **Clock point**: tên tín hiệu clock và cạnh (`posedge clk`) | P1 |
| FSM-16 | **Reset point**: tín hiệu reset, điều kiện (`!reset_n`), đồng bộ hoặc không đồng bộ, và state đích khi reset (`ST_IDLE`) | P1 |
| FSM-17 | **Interrupt point** (icon tia sét đỏ-vàng): transition ưu tiên cao nhất, có thể xảy ra từ mọi state. **Recovery state point** (hình tròn đỏ có dấu X): state đích khi FSM rơi vào giá trị không hợp lệ (nhánh `default`) | P1 |
| FSM-19 | **Wait state**: giống state thường nhưng chờ từ 2 chu kỳ clock trở lên trước khi xét transition. Project mẫu không dùng wait state, nên hạ xuống P2 | P2 |
| FSM-25 | **State Register Statements**: code người dùng thay cho câu gán state mặc định, đặt trước phần giải mã state | P2 |
| FSM-26 | **Hierarchical state** (state chứa sơ đồ con) với **entry point** / **exit point**. Chưa thấy dùng trong project mẫu | P3 |
| FSM-27 | Hỗ trợ ký hiệu Mealy, Moore và kết hợp cả hai | P1 |
| FSM-28 | **Thứ tự ưu tiên khi các action xung đột**: (1) action của transition interrupt → (2) action của transition thường → (3) state action → (4) global action → (5) giá trị Default. Nhiều interrupt trên cùng sơ đồ thì xét theo priority | P1 |
| FSM-29 | **Enable point**: tín hiệu enable cho máy trạng thái đồng bộ | P2 |
| FSM-35 | **Recovery state** chỉ áp dụng cho phần giải mã state (nhánh `default`). Recovery action được xử lý như state action. Muốn có nhánh "others" cho transition thì dùng một transition không có điều kiện | P1 |
| FSM-36 | Máy trạng thái **không đồng bộ** (không có clock, cần thuộc tính propagation delay) | P3 |
| FSM-18 | Khung text tự do: comment, và khối **default/global assignment** (ví dụ `x_cld <= x_cld;`) | P1 |

**Các phần khai báo (vùng text trên sơ đồ)**
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FSM-20 | **Global Actions**: *Pre Actions* và *Post Actions*, chèn vào trước và sau khối case của FSM | P1 |
| FSM-21 | **Module Declarations**: khai báo thêm trong module (wire, reg, localparam, …) | P1 |
| FSM-22 | **Concurrent Statements**: code Verilog tự do (`always`, `assign`) chép nguyên vào module | P1 |
| FSM-23 | **Compiler Directives**: *Pre-module* (ví dụ `` `include "dti_global_defines.vh" ``), *Post-module*, *End-module* | P1 |
| FSM-24 | **Signal Status**: bảng chỉ đọc, gồm SIGNAL, MODE (local/output), DEFAULT, RESET, SCHEME (CLKD/COMB), COMMENT. Tự cập nhật từ Signals Table | P1 |

**Signals Table** (bảng kiểu spreadsheet, có số dòng và chữ cột A, B, C, …)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| SIG-1 | Cột: **Group, Name, Mode, Type, Signed, Bounds, Delay, Value, Category, Assign, Expression, Scheme, Default, Reset, Comment** | P1 |
| SIG-2 | *Mode*: input, output, inout, local. *Type*: wire, reg, logic. *Bounds*: biểu thức range, có thể dùng parameter (`[DRAM_ADDR_WIDTH-1:0]`) | P1 |
| SIG-3 | *Category* (chỉ cho input và local; output luôn là Data): **Clock** Rising / Falling / Specify; **Reset** Async Low / Async High / Async Specify / Sync Low / Sync High / Sync Specify; **Enable** Low / High / Specify. Chọn *Specify* thì nhập biểu thức ở cột *Expression*. Mỗi máy trạng thái có 1 clock, 1 enable và **nhiều reset** | P1 |
| SIG-7 | *Assign In*: máy trạng thái song song nào gán tín hiệu này, mặc định `<auto>` (tự xác định khi generate). Chọn `<none>` thì không đặt được Scheme, Default, Reset. Cột này ẩn khi chỉ có một máy | P1 |
| SIG-8 | Tín hiệu khai báo trong Module Declarations hiện trong Signals Table dưới dạng dòng chỉ đọc | P2 |
| SIG-4 | *Scheme* (theo tài liệu State Machine):<br>• **Combinatorial**: gán trong khối output. Cần *Default* nếu không thì sinh latch. Không có reset.<br>• **Registered** (chỉ output): action gán vào tín hiệu nội bộ tổ hợp (có tiền tố/hậu tố, ví dụ `_int`), khối clocked gán tín hiệu nội bộ ra port. Cần *Default*. Reset áp vào **port thật**.<br>• **Clocked** (output và local): output thì action gán vào tín hiệu nội bộ `_cld` trong khối clocked, port nhận giá trị bằng phép gán liên tục. Reset áp vào **tín hiệu nội bộ**. Local thì gán thẳng trong khối clocked, reset áp vào chính nó. *Default* không bắt buộc; nếu không có thì giữ giá trị cũ.<br>Không đặt được Scheme cho: input, tín hiệu clock/reset/enable, tín hiệu có Assign In = `<none>`, tín hiệu trong máy kiểu 1 khối (luôn là clocked) | P1 |
| SIG-9 | Tiền tố/hậu tố của tín hiệu nội bộ cấu hình được (FSMG-17). Mặc định: Registered `_r`, Clocked `_cld`, Gated clock `_gated` | P1 |
| SIG-10 | Nếu *Default* để trống, generator dùng giá trị phù hợp với độ rộng tín hiệu | P2 |
| SIG-5 | Sắp xếp và lọc theo cột, nhóm theo *Group*, sửa trực tiếp trong ô, thêm và xóa dòng | P1 |
| SIG-6 | Bảng này là nguồn của danh sách port: sửa ở đây thì interface và symbol của unit cập nhật theo | P1 |

**Parameters Table**
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| PAR-1 | Cột: **Group, Name, Value, Comment**. Value có thể là macro (`` `CFG_DRAM_ADDR_WIDTH ``) | P1 |

### 3.7.2 Block Diagram editor (BD) – chi tiết
Rút ra từ view `protocol_controller/pc_global_controller/struct` (4 component, 1 embedded block, 112 net, 155 wire, 81 port) và các định nghĩa trong user guide.

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| BD-1 | Tiêu đề: `Project <prj>: <library>/<unit>/<view> (Block Diagram)`. Menu: File, Edit, View, HDL, Diagram, Tasks, Add, Options, Window, Help | P1 |
| BD-2 | Structure Navigator: Signal Table, Parameters Table, tên unit → Declarations/Statements, **Embedded** (danh sách embedded block). Có khung Content liệt kê đối tượng theo loại | P1 |
| BD-3 | **Component instance**: hình chữ nhật có 3 nhãn (library, tên component, tên instance), port là tam giác trên cạnh, **gán parameter** cho từng instance (ví dụ `WIDTH = MC_COUNTER_WIDTH`) | P1 |
| BD-4 | **Block**: như component nhưng interface động, lấy từ các tín hiệu nối vào. Double-click thì mở hoặc tạo view con | P2 |
| BD-5 | **Embedded block**: khung chứa HDL text (ví dụ `global_assignments` chứa `assign` và `always`), **không tạo thêm cấp phân cấp**. Code được chép thẳng vào module sinh ra | P1 |
| BD-6 | **Port I/O** của module: cờ ngũ giác vào/ra ở mép sơ đồ | P1 |
| BD-7 | **Net / Wire / Bus**: net là tín hiệu có tên và kiểu, wire là đoạn dây vẽ. Bus vẽ nét đậm. Nhãn tên net đặt trên dây | P1 |
| BD-8 | **Net connector**: nối các net cùng tên, hoặc làm đầu chờ (dangling) cho net cố ý để trống. Hiển thị là vòng tròn đỏ | P1 |
| BD-9 | **Global connector**: tín hiệu nối vào đây (thường là clock, reset) coi như nối tới mọi block | P2 |
| BD-10 | **Ripper**: tách hoặc gộp lát (slice) của bus. **Bundle**: nhóm nhiều tín hiệu thành một đường | P2 |
| BD-11 | **Generate frame**: `FOR` và `IF`/`ELSE` bao quanh instance để nhân bản hoặc thêm có điều kiện (ví dụ `FOR : ps_chan_num` thấy trong Design Hierarchy) | P1 |
| BD-12 | Rê chuột lên instance thì hiện tooltip: component (`library.unit`), view name, view type (ví dụ `STATE_MACHINE`) | P2 |
| BD-13 | Signal Table và Parameters Table của block diagram dùng chung cách làm với FSM (SIG, PAR) | P1 |
| BD-14 | **Panel** (vùng có tên), **port map frame** | P3 |
| BD-15 | Sinh HDL structural: port, parameter, khai báo net, instance (port map và parameter theo kiểu đặt trong Verilog Options), code của embedded block, compiler directives, generate frame | P1 |
| BD-16 | Hộp thoại **BD Object Properties**. Cây bên trái gồm các loại đối tượng: Components (Parameters, Text Visibility, PortMap Frame, Attributes, Appearance), Blocks, Embedded Blocks, ModuleWare, ExternalIPs, Signals, Bundles, Protocols, PortIOs, Frames, Comment Text, Comment Graphics, User Declarations, User Properties. Loại nào không có trong vùng chọn thì làm mờ | P1 |
| BD-17 | Trang **Component Parameters**: tiêu đề `Instance "<inst>" of module "<module>"`. Danh sách trái là parameter của module kèm giá trị mặc định (lọc *Symbol parameters only* hoặc *All parameters*). Danh sách phải là các parameter **ghi đè** cho instance này (Name, Value), có nút *Add*, *Add All*, *Remove*, *Clear*. Chỉ parameter ở danh sách phải được sinh vào `#( … )` của instance | P1 |
| BD-18 | Trang **Component Text Visibility**: *Show parameter values*. Trường hiển thị cạnh port: Port Name, Type Constraint (Type Name, Signed), Value. *Display Port and Declaration information on the same line*. *Selectable Text*. Ô *Format Preview* | P2 |
| BD-19 | Trang Attributes, Appearance (màu, nét, font) của component | P3 |

### 3.7.3 ModuleWare (MW)
ModuleWare là thư viện các khối có tham số, độc lập công nghệ: cổng logic, mux, decoder/encoder, adder, comparator, shifter, flip-flop, latch, … Mỗi khối được đặt trên block diagram và **sinh code inline** (tín hiệu nội bộ có tiền tố `mw_`), không phải instance của module ngoài. Nguồn: *ModuleWare Reference*. Project mẫu có library `moduleware` (protected) nhưng hai view đã phân tích không dùng khối nào.

| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| MW-1 | Thư viện ModuleWare: đặt khối lên block diagram, đặt tham số (độ rộng, số input, cực tính, kiểu reset/clock/enable), sinh Verilog/SystemVerilog inline | P2 (người dùng xác nhận: có thể dùng, làm sau) |
| MW-2 | Ưu tiên nhóm khối hay dùng: Logic, Constants, Combinatorial (mux, decoder), Bit Manipulation (merge, split, tap), Register (adff) | P2 |
| MW-3 | Import khối ModuleWare từ file `.bd` của tool cũ | P2 |

**Sinh code từ FSM**
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| FSM-30 | Sinh ra một module Verilog/SV gồm: compiler directives, port từ Signals Table, parameter, module declarations, khai báo state, khối tuần tự (clocked), khối tổ hợp (next state, actions), concurrent statements, mỗi máy trạng thái một bộ | P1 |
| FSM-31 | Tín hiệu *clocked* được sinh thành cặp tín hiệu kế tiếp/thanh ghi (kiểu `<name>_cld`), có giá trị reset và default | P1 |
| FSM-32 | Phong cách mã hóa state cấu hình được: `localparam`, `parameter` hoặc SV `enum`; binary, one-hot, gray | P2 |
| FSM-33 | Phong cách code sinh ra ở chế độ Verilog phải khớp với code mà tool cũ đang sinh (xem GEN-11 và [codegen-reference.md](codegen-reference.md)) | P1 |
| FSM-34 | Sinh FSM gồm 4 khối có tên cố định: `next_state_block_proc`, `output_block_proc`, `clocked_block_proc`, `clocked_output_proc`. Điều kiện interrupt bọc ngoài cả 3 khối đầu. Nhánh `default` của case trạng thái là recovery state | P1 |

**Thuộc tính sinh code của State Machine** (hộp thoại *State Machine Properties*, theo tài liệu State Machine). Cột cuối là giá trị mà project mẫu đang dùng.

| ID | Thuộc tính | Lựa chọn | Mẫu `gc_control_fsm` | Ưu tiên |
|---|---|---|---|---|
| FSMG-1 | Số khối always | 3 (next state, output, clocked), 2 (gộp next state và output), 1 (một khối clocked duy nhất). Khối output bị bỏ nếu chỉ có phép gán mặc định | 3 | P1 |
| FSMG-2 | Kiểu giải mã | Case, If, One-Hot. Có casex/casez khi mã hóa thủ công | Case | P1 |
| FSMG-3 | Kiểu phép gán | Mixed (`<=` trong khối clocked, `=` trong khối tổ hợp), Blocking, Non-blocking | Mixed | P1 |
| FSMG-4 | **Mã hóa state** (trang *Encoding*) | **Scheme**: *Specified* hoặc *Auto*. *Pragma* (ví dụ `syn_encoding`) chọn từ danh sách.<br>**Style**: Sequential, 1-Hot, 2-Hot, Gray, Johnson, Manual.<br>**Bảng mã**: State Name, giá trị mã, dòng tổng (số state, số bit). Ở chế độ Manual thì sửa trực tiếp được, kể cả giá trị don't care; kéo thả để đổi mã giữa các state; sắp xếp theo tên hoặc theo mã.<br>Tùy chọn: *Parameter Declaration Range* (ghi `[4:0]` trong khai báo), *Add state vector pragma*, *Add syn_preserve pragma*.<br>*Output Encoded* (chỉ cho máy Moore thuần), kèm *Use Local signals in encoding* | Specified, Sequential (`ST_RUN = 00000` … 23 state, 5 bit), không pragma | P1 (tất cả style), P2 (pragma, output encoded) |
| FSMG-5 | Tên tín hiệu state | Mặc định `current_state`, `next_state`, đổi được | Mặc định | P1 |
| FSMG-6 | Interrupt | Sinh dạng if-then-else độc quyền (bọc ngoài) hoặc dạng override (đặt sau case) | if-then-else | P1 |
| FSMG-7 | Register state actions on next state | Bật/tắt (giải mã theo next state để bỏ trễ 1 chu kỳ) | Tắt | P2 |
| FSMG-8 | Pragma | `full_case`, `parallel_case`, pragma cho state vector, pragma reset | Không | P2 |
| FSMG-9 | Gán state variable ra một output port | Bật/tắt | Tắt | P3 |
| FSMG-10 | Delay khi gán current state (không tổng hợp được) | Số đơn vị thời gian | Không | P3 |
| FSMG-11 | Wait state settings | Độ rộng bộ đếm wait | – | P2 |
| FSMG-12 | Instrument HDL cho animation | Ngoài phạm vi (cần simulator) | – | – |
| FSMG-13 | Bố cục hộp thoại *State Machine Properties* | Cây trang bên trái: **Generation** (→ Advanced), **Encoding**, **Statement Blocks**, **Declaration Blocks** (→ Pre/Post User Declarations), **Internal Signals**. Tiêu đề kèm tên máy, ví dụ `(dram_control_fsm)` | – | P1 |
| FSMG-14 | Trang *Generation* | Machine: Synchronous / Asynchronous (+ Prop Delay). Generation Style: 1/2/3 Always Blocks, If / One-Hot / Case, với Case thì chọn `case` / `casex` / `casez`. Output Encoded. Register state actions on next state. Default State Assignment. Full/Parallel Case Pragmas (chọn chuỗi pragma, ví dụ `// pragma parallel_case full_case`). Assignment type: Mixed / Blocking / Non-blocking | 3 khối, Case, `case`, Mixed, các ô khác tắt | P1 |
| FSMG-15 | Trang *Statement Blocks* | **Concurrent Statements**, **State Register Statements**, **Global Actions** gồm *Pre Actions*, *Post Actions* và *Location of non-driving actions* (ví dụ Output Process). Mỗi khối có ô **Visible** (hiện trên sơ đồ hay không) và nút mở editor | Concurrent Statements có code, các khối khác trống | P1 |
| FSMG-16 | Trang *Declaration Blocks* | Module Declarations, Pre/Post User Declarations | – | P1 |
| FSMG-17 | Trang *Internal Signals* | Affix dùng làm **Prefix** hoặc **Suffix**. **Registered Affix** (mặc định `r` → `X_r`), **Clocked Affix** (`cld` → `X_cld`), **Gated clock Affix** (`gated` → `X_gated`). *Use initial value of original signals* | Suffix, `r`, `cld`, `gated` | P1 |

**Hai lựa chọn độc lập với nhau:** *style mã hóa* (FSMG-4: Sequential, 1-Hot, Gray, …) quyết định **giá trị** của từng state. *Kiểu khai báo* (GEN-19: `parameter`, `localparam`, `enum`) quyết định **cú pháp** khai báo các giá trị đó. Ví dụ, Gray kết hợp với `enum` sinh ra `typedef enum logic [4:0] {ST_RUN = 5'b00000, ST_DRAIN = 5'b00001, ST_SRE = 5'b00011, …}`.

Khi sinh **SystemVerilog**: kiểu 1 khối thành `always_ff`. Kiểu 2 và 3 khối dùng `always_comb` cho phần tổ hợp. Mã hóa Sequential/Manual có thể sinh `typedef enum` với giá trị tường minh. Pragma `full_case`/`parallel_case` có thể thay bằng `unique`/`priority case` nếu người dùng chọn (GEN-13).

### 3.8 Trực quan hóa code có sẵn (VIS)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| VIS-1 | Từ một module text, tự sinh **sơ đồ khối chỉ để xem**: instance, port, kết nối | P1 |
| VIS-2 | Nhận diện FSM trong code và vẽ state diagram để xem | P3 |
| VIS-3 | Click vào đối tượng trên sơ đồ thì nhảy tới dòng code tương ứng | P2 |
| VIS-4 | Chuyển một visualization thành view đồ họa có thể sửa | P3 |

### 3.9 Quản lý phiên bản (VM)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| VM-1 | Tích hợp **Git**: hiển thị trạng thái (modified, new, untracked, conflict) dạng overlay trong Explorer | P2 |
| VM-2 | Thao tác trên design object: add, commit, revert, diff, log/history. View đồ họa đi kèm file meta tự động | P2 |
| VM-3 | Chọn phạm vi theo phân cấp: commit cả cây con của một design unit | P3 |
| VM-4 | SVN | P3 |

### 3.10 Thiết lập và task (PREF / TSK)
| ID | Yêu cầu | Ưu tiên |
|---|---|---|
| PREF-1 | Có 2 tầng preference: **team** (file dùng chung) và **user** (`~/.config/vietsemi-hdl-studio`) | P1 |
| PREF-2 | Hộp thoại Preferences cho editor, generate, style và đặt tên file | P1 |
| PREF-3 | **Main Settings – General**: tự chuyển tên design unit/view sang chữ thường; nút toolbar *Remain active* / *Activate once only*; hiển thị tên file dạng logic hoặc tên thật; *Single User* / *Team Mode*; thư mục tạm; file thuộc tính project; ngôn ngữ mặc định cho view mới (đồ họa: Verilog 2005, text: SystemVerilog) | P1 |
| PREF-4 | **Verilog Options – File**: danh sách đuôi file hợp lệ, đuôi mặc định cho source, file sinh ra và SystemVerilog; quy tắc tên file source (`%(module_name).%(ext)`, giữ nguyên hoa/thường) và file sinh ra (`%(unit).%(ext)`, luôn chữ thường); search path mặc định | P1 |
| PREF-5 | **Verilog Options – Style**: độ rộng tab; `begin`/`else` xuống dòng; dòng trống quanh comment; nhãn cho khối `always`/`initial` (tiền tố, hậu tố, hoa/thường); kèm property vào code sinh ra; tên view testbench mặc định; khởi tạo parameter của symbol trên instance; pragma mẫu trên khai báo parameter; **Verilog 2005**: port ANSI-C hoặc list (kiểu khai báo gộp/tách), parameter ANSI-C hoặc list, gán parameter instance **Named** hoặc **Positional**, sensitivity list ngăn cách bằng dấu phẩy hoặc `or`, cho phép `@*` | P1 |
| PREF-6 | **Verilog Options – Headers**: header template riêng cho từng loại view (Block Diagram, State Diagram, …) với biến `%(year)`, `%(project_name)`, `%(library)`, `%(unit)`, `%(graphical_source_author)`, `%(graphical_source_date)`, `%(graphical_source_time)`, …; tùy chọn chèn thông tin generate sau header | P1 |
| PREF-7 | Verilog Options – Default Directives, Default Packages | P2 |
| PREF-8 | **Giá trị mặc định của tool mới lấy theo cấu hình hiện tại của nhóm** (xem bảng ngay dưới), để code sinh ra không bị khác so với tool cũ | P1 |
| PREF-9 | Đọc preference của nhóm từ resource file của tool cũ trong `$HDS_TEAM_HOME` (cần file mẫu) | P2 |

**Cấu hình hiện tại của nhóm (từ ảnh chụp, dùng làm mặc định):**

| Mục | Giá trị |
|---|---|
| Ngôn ngữ mặc định | Tool cũ: view đồ họa Verilog 2005, text SystemVerilog. **Tool mới: SystemVerilog cho cả hai** (GEN-10), vẫn chọn được Verilog |
| Đuôi file hợp lệ | `v vlg verilog vo sv svh`. Source: `v`, sinh ra: `v`, SystemVerilog: `sv` |
| Tên file source | `%(module_name).%(ext)`, giữ nguyên hoa/thường |
| Tên file sinh ra | `%(unit).%(ext)`, luôn chữ thường |
| Tab width | 2 |
| `begin`/`else` xuống dòng, dòng trống quanh comment, nhãn khối always | Tắt (hậu tố mặc định `_PROC`, chữ thường) |
| ModuleWare | Non-blocking, tiền tố tín hiệu `mw_` |
| Testbench view name | `struct` |
| Port / Parameter | ANSI-C / ANSI-C |
| Gán parameter instance | Named |
| Sensitivity list | Dấu phẩy, không dùng `@*` |
| Header Block Diagram | Khối comment bản quyền công ty với Project, Module (`%(library).%(unit)`), Author, Date |
| Thông tin generate sau header | Tắt |
| TSK-1 | Task Manager: định nghĩa task chạy lệnh hoặc script ngoài cho đối tượng đang chọn, có biến thay thế đường dẫn và tên. Output hiện trong Log | P3 |

---

## 4. Yêu cầu phi chức năng (NFR)

| ID | Yêu cầu |
|---|---|
| NFR-1 | Chạy trên **CentOS Stream 9** (x86_64). Sau đó mở rộng sang CentOS 7 và 10 |
| NFR-2 | Công nghệ: Python 3.10+ (đang dùng 3.12), Qt 6 qua **PySide6**. Parser SystemVerilog dùng **slang** (pyslang). Đóng gói bằng PyInstaller |
| NFR-3 | Chạy được qua X11 forwarding, VNC và XWayland. Không bắt buộc OpenGL |
| NFR-4 | Hiệu năng: mở project khoảng 2.000 file và 200.000 dòng trong dưới 10 giây. Parse lại 1 file trong dưới 300 ms |
| NFR-5 | Mọi file project, preference và view đồ họa đều là **text**, merge được bằng Git |
| NFR-6 | Không làm mất dữ liệu: tự lưu nháp và khôi phục khi crash. Không ghi đè file HDL mà người dùng đã sửa tay nếu chưa xác nhận |
| NFR-7 | Có chế độ dòng lệnh (CLI) cho import, generate và report |

---

## 5. Câu hỏi mở

1. ~~Chốt nguyên tắc lưu trữ ở mục 2~~ (đã chốt 2026-10-30).
2. ~~Có cần tương thích với `.hdp` và file đồ họa của tool cũ?~~ Có, xem PRJ-10 đến PRJ-17 và IMP-7 đến IMP-12. **Còn thiếu:** file `.v` mà tool cũ sinh ra cho `gc_control_fsm` và `gc_control_timer`, để đối chiếu phong cách code (IMP-10, FSM-33).
3. Mức hỗ trợ SystemVerilog: chỉ phần synthesizable, hay cả class và UVM?
4. ~~Có nhiều người dùng không?~~ Có (file `.lck` chứa user và host), xem PRJ-16 và PRJ-17.
5. Thứ tự ưu tiên giữa Block diagram editor và State machine editor.

---

## 6. Kết quả đối chiếu ảnh chụp với user guide

Nguồn: *HDL Designer Series User Manual v2024.2*, gồm các phần Glossary, "Opening Design Unit Views", "Main Settings Dialog Box", "Verilog Options Dialog Box", Appendix J. Riêng chi tiết các graphical editor nằm trong *Graphical Editors User Manual*, một tài liệu khác chưa có.

| Nội dung | Kết quả | Ghi chú |
|---|---|---|
| Interrupt point (tia sét đỏ-vàng) | ✅ Đúng | Nối ngầm tới mọi state, ưu tiên cao hơn mọi transition khác. Ở sơ đồ cấp cao nhất thì áp dụng cho cả máy phân cấp |
| Recovery state point (tròn đỏ dấu X) | ✅ Đúng | State đích khi không có phép gán state hợp lệ |
| Wait state | ✅ Đúng | Trễ từ 2 chu kỳ clock trở lên |
| Link, Junction | ✅ Đúng | Đã bổ sung: junction cũng dùng trên block diagram làm điểm nối net |
| File `.lck` | ✅ Đúng | Tạo khi mở view đồ họa, xóa khi đóng. Nếu view đang bị khóa hoặc chưa đóng đúng cách (ví dụ mất điện) thì hỏi người dùng: gỡ khóa hay mở chỉ đọc. Nội dung bên trong file là quan sát của mình, user guide không mô tả |
| Scheme của tín hiệu | ⚠️ **Đã sửa** | Trước ghi 2 loại (clocked/comb). User guide có **3 loại**: Combinatorial, Registered, Clocked (SIG-4) |
| Type trong Design Explorer | ⚠️ **Đã sửa** | Trước ghi Module/Component. User guide còn có **Block** (interface động) và *unknown* (EXP-14) |
| Thứ tự transition | ➕ Bổ sung | Phân biệt *priority* (transition kiểu IF, `OTHERS` luôn xét cuối) với *transition order* (nhánh CASE, quan trọng trong Verilog) |
| Embedded block | ✅ Đúng | Không tạo thêm cấp phân cấp (BD-5) |
| Main Settings, Verilog Options | ✅ Đúng | Các trường trong ảnh khớp với bảng mô tả trong user guide |
| Structure Navigator, Content List | ✅ Đúng | Theo *Graphical Editors User Manual* |
| Signals Table: Name, Mode, Type, Signed, Bounds, Delay, Value, Comment | ✅ Đúng | Theo *Graphical Editors User Manual* |
| Sinh SystemVerilog từ view đồ họa | ✅ Xác nhận tool cũ **không** làm được | Chỉ hỗ trợ SV ở mức text. Port SV bị ép về kiểu Verilog-95 |
| Wait state trong project mẫu | ⚠️ **Đã sửa** | Trường `wait` trong file `.sm` chỉ là text ẩn mặc định. Project mẫu không dùng wait state |
| Các cột riêng của FSM: Category, Assign In, Expression, Scheme, Default, Reset | ✅ Đã đối chiếu | Theo *State Machine User Manual*. Đã chi tiết hóa SIG-3, SIG-4, SIG-7 đến SIG-10 |
| Scheme của tín hiệu local | ⚠️ **Đã sửa** | Local chỉ có Combinatorial hoặc Clocked. Registered chỉ dành cho output |
| Cấu trúc code FSM của mẫu | ✅ Khớp | 3 khối always, kiểu Case, phép gán Mixed, mã hóa Sequential, interrupt dạng if-then-else (FSMG-1 đến FSMG-6) |
