# Đối chiếu HDL Studio với *HDS Graphical Editors User Manual* (v2024.2)

Nguồn: `HDS_2024.2/docs/pdfdocs/hds_graph_ed_user.pdf` (cùng nội dung với bản HTML `htmldocs/hds_graph_ed_user`).
Thứ tự giữ nguyên như mục lục của user guide để kiểm tra lần lượt.

Ký hiệu:

| | Nghĩa |
|---|---|
| ✅ | Đã làm, khớp mô tả của user guide |
| 🟡 | Đã làm một phần (ghi rõ phần thiếu) |
| ❌ | Chưa làm, thuộc phạm vi tool (quản lý / sinh code / bảo trì Verilog-SV) |
| ⛔ | Ngoài phạm vi đã thống nhất (VHDL, IBD, Truth Table, Flowchart, mô phỏng, test bench...) |
| 📷 | Cần ảnh chụp HDS để làm cho đúng (xem danh sách ở cuối) |

> State Diagram có user guide riêng (`hds_state_ed_user.pdf`), sẽ đối chiếu ở một tài liệu khác.

---

## 1. Introduction to HDS Graphical Design Creation Editors

### Design Creation Editors
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| DesignPad Text Editor | 🟡 | Có editor HDL riêng (số dòng, find/replace, go to line, kiểm tra cú pháp slang, mở gvim/emacs). Không phải DesignPad |
| Block Diagram and IBD View Editors | 🟡 | Block Diagram có; IBD ⛔ |
| Component Interface Editor | ❌ | Chưa có Symbol / Tabular IO (xem mục 7) |
| State Diagram and ASM Editors | 🟡 | State Diagram có; ASM ⛔ |
| Flow Chart Editor, Truth Table Editor | ⛔ | |

### Using the Graphical Editors Common Features
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Hardware Description Language Overview | ✅ | Verilog 2005 / SystemVerilog |
| Setting Package References / Package List Dialog Box | ⛔ | Chỉ dùng cho VHDL |
| Verilog Compiler Directives Dialog Box | 🟡 | Có tab *Compiler Directives* (pre-module / post-module / end-module). Chưa có dạng dialog 📷1 |
| Opening the Parent View (Open Up) | ❌ | Nút có nhưng làm mờ |
| Editing the Parent Interface | ❌ | |
| Reusing the Current Window (Back / Forward) | ❌ | Nút có nhưng làm mờ |
| Save As Design Unit View Dialog Box | ❌ | Block Diagram chưa có Save As 📷2 |
| Backing Up and Recovering Automatically | ✅ | Autosave 30 s, hỏi khôi phục sau khi tool bị tắt đột ngột |
| Selecting Objects in a Diagram or Table Editor | ✅ | Select / Select Text / Select Shapes, Shift/Ctrl+click, kéo khung, Alt+click chọn một đoạn net |
| Find and Replace Dialog Box (Advanced Options) | ❌ | Nút Find làm mờ trong editor đồ họa 📷3 |

### Object Linking and Embedding
| About OLE Object Import / Opening an OLE View | ⛔ | |
|---|---|---|

### HDL Generation
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Generating HDL From Graphical Views | ✅ | Single / Through Blocks / Through Components / Through Design Root; bảo vệ ghi đè file |
| Setting a Black Box for Synthesis | ❌ | Mục menu có nhưng làm mờ |
| Viewing the Generated HDL | ✅ | Ctrl+G |

---

## 2. Graphical Editor Windows

### Diagram Editor Windows
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Main Settings Dialog Box - Diagrams Tab | ❌ | Mới có Preferences chung. Chưa có tuỳ chọn Diagrams (strokes, auto-repeat, ...) 📷4 |
| Master Preferences - Background Page | ❌ | Lưới và màu nền đang cố định 📷5 |
| Moving and Copying Diagram Objects | 🟡 | Kéo / Ctrl+mũi tên / Shift khoá hướng / di chuyển một đoạn net / bám lưới 1000 đơn vị đều có. Thiếu **Move Here** (chuột phải) |
| Aligning or Distributing Objects | ❌ | 📷6 |
| Rotating and Flipping Objects | ❌ | Mục Rotate/Flip có nhưng làm mờ |
| Comment Text and Graphics Layering / Grouping | ❌ | |
| Adding Comment Text | ❌ | Nút Add Comment Text làm mờ 📷7 |
| Editing Text Properties | ❌ | |
| Requirement Reference (3 mục) | ⛔ | |
| Editing Text on a Diagram | 🟡 | Chỉ sửa tên net tại chỗ (double-click). Tên instance, tên block, text embedded chưa sửa tại chỗ |
| Editing Text in the Text Editor | 🟡 | Embedded block sửa trong khung Properties |
| Movement of Text From an Object | ❌ | Text của component / net chưa kéo rời ra được (nhãn net đọc đúng vị trí từ file .bd nhưng chưa kéo được) |
| Text Visibility for Objects / Changing Text Visibility | 🟡 | Có cho Component (Port Name, Type Constraint, Value...) và PortIO. Chưa có cho Signal (Signal Display Control) 📷8 |
| Using Comment Graphics | ❌ | |
| Adding a Title Block | ❌ | 📷9 |
| About Object Tips | 🟡 | Bật/tắt được; nội dung tip còn đơn giản (tên net) 📷10 |
| Panels Overview (5 mục) | ❌ | Nút Add Panel làm mờ |
| Editing Route Points | ✅ | Kéo ô vuông, gộp điểm thẳng hàng, Add Route / Remove Route / Remove All Routes, ô vuông cố định kích thước khi zoom |
| Edit Appearance Dialog Box | 🟡 | Có cho Component và PortIO (màu, fill style, line style/width). Chưa có cho net, frame, text; chưa có palette 25 màu 📷11 |

### Table Editor Windows
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Main Settings Dialog Box - Tables Tab | ❌ | |
| Exporting a Table | ❌ | |

### Các cửa sổ khác
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Diagram Browser Subwindow | ❌ | Block Diagram chưa có Structure Navigator + Content (State Diagram có Structure Navigator) 📷12 |
| Using Groups in the Content Pane | ❌ | |
| Using Flow Help | ⛔ | |
| Signals Table Overview / Interface | 🟡 | Có tab Signal Table. Chưa đối chiếu cột và thao tác với HDS 📷13 |
| Adding Port or Local Signal Declarations | 🟡 | Thêm được từ bảng; chưa kiểm tra đủ trường hợp |
| Comments Dialog Box | 🟡 | Có Comments... trên menu net (một dòng); HDS cho nhiều dòng |
| Filtering the Signals Table Columns / Grouping Signal Rows | ❌ | |

---

## 3. Block Diagram and IBD Views

### Block Diagram and IBD Views Editors
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Assigning Automatic Instance Names | 🟡 | Tên instance mới lấy theo tên component; chưa có preference Manual/Automatic (`U_0`, `%{unit}`) |
| Instantiating a Block | ❌ | Nút Add Block làm mờ 📷14 |
| Instantiating a Component | ✅ | Chọn từ project, hoặc từ file .v/.sv |
| Instantiation of Verilog / SystemVerilog Text Components | ✅ | |
| ModuleWare (3 mục) | ⛔ | Đã thống nhất làm sau |
| External HDL Model Instantiation / Add External IP / Soft Pathname / Updating | ❌ | Add Component *From HDL file* gần giống; chưa có dialog External IP 📷15 |
| Adding an Embedded Block | ✅ | |
| Embedded View Display and Creation | ❌ | |
| Editing Embedded HDL Text | 🟡 | Sửa trong khung Properties, chưa sửa tại chỗ trên sơ đồ |
| Updating an Instance / Update Interface Dialog Box | 🟡 | Có *Update ▸ Interface*. Chưa có dialog Update Interface 📷16 |

### Kiểm tra và Object Properties
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Setting Design Checking Options / Through Hierarchy | 🟡 | Có Run Design Rule Checks (cảnh báo kết nối + slang). Chưa có options, chưa chạy theo hierarchy |
| BD Object Properties - Components Page | ✅ | Components / Parameters / Text Visibility / PortMap Frame / Attributes / Appearance |
| BD Object Properties - Blocks Page | ❌ | 📷17 |
| BD Object Properties - Embedded Blocks Page | ❌ | 📷18 |
| BD Object Properties - ModuleWare / ExternalIPs Page | ⛔ / ❌ | |
| BD Object Properties - Signals Page | 🟡 | Có Style, Name, Type, Bounds, Delay, Value, Expansion, Charge Strength, Apply changes to. Chưa có Slice/Index; chưa có các trang Text Visibility / Attributes / Comments / Appearance của Signal 📷19 |
| BD Object Properties - Protocols / Bundles Page | ❌ | |
| BD Object Properties - Port IOs Page | ✅ | Mode In/Out/InOut, Text Visibility, Appearance |
| BD Object Properties - Frames Page | ✅ | |
| BD Object Properties - Requirement Reference / Comment Graphics | ⛔ / ❌ | |
| BD Object Properties - User Declarations Page | ❌ | 📷20 |
| BD Object Properties - User Properties Page | ❌ | |
| Setting the Scope for Net Changes | 🟡 | Menu *Scope For Changes* có; chỉ *Entire Net in diagram* hoạt động |
| Attributes Dialog Box | 🟡 | Trang Attributes của Component có; ghi vào HDL dạng chú thích |
| Net Propagation and Modification (4 dialog) | ❌ | Insert Net / Remove Net làm mờ |

### Các mục còn lại của chương
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Ordering Port and Signal Declarations | 🟡 | Đang sắp theo mode rồi theo tên; chưa có thứ tự thủ công (Port/signal ordering: Automatic / Manual) |
| Removing Design Hierarchy / Add Hierarchy Dialog Box | ❌ | 📷21 |
| Generics and Parameters (10 mục) | 🟡 | Có bảng Parameters của sơ đồ; trang Parameters của instance đọc đúng bảng symbol (giữ nguyên `` `CFG_... ``). Chưa có grouping/filtering, chưa có đồng bộ Generics/Parameters |
| Opening Block and Component Views | ✅ | Open Down, double-click, Open As |
| New Block Diagram or IBD View Initialization | 🟡 | *New Design Content* tạo được Block Diagram mới, chọn ngôn ngữ Verilog 2005 / SystemVerilog (xem [uart-compare.md](uart-compare.md)). IBD ngoài phạm vi |
| Mixed Language Designs | ⛔ | |

---

## 4. Block Diagram Editor

### Block Diagrams
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Block Diagram Notation | 🟡 | Component, PortIO, net, dangling connector, frame giống HDS; block, bus ripper, bundle, global connector chưa có |
| Blocks and Components | 🟡 | Component có; block chưa |
| Embedded Blocks and Embedded Views | 🟡 | |
| Signals, Buses, and Bundles | 🟡 | Signal và bus (nét dày khi có bounds) có; bundle chưa |
| Ports and Signals | ✅ | |
| Port Display Control Dialog Box | ✅ | Là trang Text Visibility (name : type [bounds] #delay) |
| Signal Display Control Dialog Box | ❌ | 📷8 |

### Addition of Nets on a Block Diagram
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Net Routing | 🟡 | 4 chế độ River / Avoidance / Diagonal / Dog Leg với phím `z` khi kéo PortIO; dây vào chân từ phía sau. Chưa có preference *Default Mode*, *Port IO Stub Routing*, *Real-time Keys* |
| Adding a Signal or Bus on a Block Diagram | 🟡 | Add Signal có; Add Bus / with Port / with Ripper làm mờ |
| Adding a Protocol | ❌ | |
| Ripping From a Bus | ❌ | 📷22 |
| Adding Signal Stubs | ✅ | Ctrl+F10 / Shift+F10 |
| Adding a Bundle / Ripping From a Bundle | ❌ | |
| Using HDL Text to Combine or Split Signals | 🟡 | Embedded block có thể dùng; chưa kiểm tra đúng ví dụ của guide |
| Adding Ports on a Block Diagram | 🟡 | In / Out có; InOut qua Change Mode; Buffer ⛔ (VHDL); Master/Slave ❌ |
| Adding a Global Connector | ❌ | 📷23 |
| Connecting Overlapping Nets (Connect Alt+C) | ❌ | Mục Connect làm mờ |
| Net Connection to a Block or Component | ✅ | Kéo đầu dây thả vào chân / PortIO, tự đặt tên |
| Net Connection to a Port Map Frame | 🟡 | Có trang PortMap Frame và mapping khi sinh code; chưa vẽ khung port map trên sơ đồ 📷24 |
| Highlighting a Net on a Block Diagram | 🟡 | Single level có; Hierarchical chưa |

### Logic Shape Notation
| Changing the Shape / Choosing a Standard Shape / Hiding Ports / Not or Clocked Ports | ❌ | Chỉ có hình chữ nhật 📷25 |
|---|---|---|

### Structural Diagram Master Preferences Dialog Box
| ❌ | Chưa có (default routing, tên mặc định sig0/dbus0, instance name Manual/Automatic, hiển thị signal, view icon...) 📷26 |
|---|---|

---

## 5. IBD View Editor
Toàn bộ chương ⛔ (IBD không thuộc phạm vi đã thống nhất).

---

## 6. Port Map and Generate Frames
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Adding a Port Map Frame / Port Map Settings Dialog Box | 🟡 | Có dữ liệu và sinh code; chưa vẽ khung, chưa có Port Map Settings dialog 📷24 |
| Adding a Generate Frame | ✅ | FOR / IF / ELSE (F6 / Shift+F6 / Alt+F6) |
| Using Generate Frames for Repeating Instances | ✅ | Instance trong FOR frame thành mảng instance, khớp file HDS sinh ra (`dc_wm_detect` khớp từng byte) |
| Using Generate Frames for Repeating Structures | 🟡 | Embedded block trong FOR frame sinh `generate for`; chưa có file HDS mẫu để đối chiếu |
| Using Generate Frames for Conditional Structures | ✅ | `` `ifdef/`else/`endif `` và `generate if` |
| Using a BLOCK Generate Frame | ⛔ | VHDL |
| Using Nested Generate Frames | 🟡 | Dữ liệu hỗ trợ lồng nhau; chưa thử với sơ đồ thật |
| BD Object Properties Dialog Box - Frames Page | ✅ | |

---

## 7. Component Interface Views
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Opening a Component Interface | ❌ | View *symbol* hiện trong cây nhưng chưa mở được |
| Tabular IO and Symbol Views / Notation / Adding Ports / Grouping / Cell Edit Appearance | ❌ | 📷27 |
| Symbol Notation / Adding and Modifying Ports / Customizing a Symbol | ❌ | 📷27 |
| Port Declaration Modifications (5 mục) | ❌ | Có Update Interface từ HDL nhưng chưa sửa được từ symbol |
| Symbol and Interface Object Properties (2 tab) | ❌ | |
| Interface Master Preferences Dialog Box | ❌ | |

---

## 8. Truth Table Editor
⛔

## 9. Graphical Rendering
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Design Extraction / Convert to Graphics Wizard / Visualizing HDL Text | ❌ | Mục menu Convert To Graphics / Visualize Code As làm mờ. Có thể cần cho "maintain code" — cần anh/chị quyết định |
| Updating a Graphics View From Generated HDL | ❌ | |
| Block Diagram Layout and Routing / Automatic Routing | ❌ | Autoroute làm mờ |

## 10. Flowchart Editor, 11. Simulation and Animation, 12. Test Benches
⛔

## 13. Reference and Keyboard Shortcuts
| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Mnemonic Keys | ✅ | Theo bảng của guide (S, T, L, C, E, I, O, B, U, N, G, F...) |
| Command Auto-Repeat | ✅ | Lệnh Add lặp tới khi Esc / chuột phải; Ctrl khi chọn lệnh để thêm một lần |
| Strokes | ❌ | Kéo chuột giữa để ra lệnh chưa có |
| Diagram View Editing Commands and Shortcuts | ✅ | Home, Shift+Home, Shift+Up/Down, Zoom Last, Ctrl+mũi tên, Esc, F2, Alt+Enter... (thiếu Ctrl+H Replace, Ctrl+P Print) |
| Text Editing Shortcuts | 🟡 | Trong editor HDL; chưa có cho text trên sơ đồ |
| Block Diagram and IBD Commands and Shortcuts | 🟡 | Phím đã gán đúng; các lệnh chưa làm thì làm mờ |
| Table View Editing Commands and Shortcuts | 🟡 | |
| State Diagram Editing Commands and Shortcuts | ✅ | Đối chiếu ở tài liệu State Diagram |
| ASM / Flow Chart / Symbol / Tabular IO shortcuts | ⛔ / ❌ | |
| Mouse Buttons | 🟡 | Trái chọn/kéo, giữa pan, phải menu/kết thúc lệnh; strokes chưa có |

---

## Ảnh cần chụp từ HDS

Mỗi ảnh nên chụp cả cửa sổ (hoặc cả dialog) ở trạng thái mặc định; nếu dialog có nhiều trang thì chụp từng trang.

| # | Cần chụp | Dùng cho |
|---|---|---|
| 1 | Diagram ▸ Compiler Directives (dialog) | Verilog Compiler Directives |
| 2 | File ▸ Save As trong Block Diagram | Save As Design Unit View |
| 3 | Edit ▸ Find và Edit ▸ Replace trong Block Diagram (bấm *More*/Advanced) | Find and Replace |
| 4 | Options ▸ Main ▸ tab **Diagrams** (và tab General) | Main Settings |
| 5 | Options ▸ Master Preferences ▸ trang **Background** | Lưới / nền |
| 6 | Menu Arrange (Align, Distribute, Rotate, Flip) khi chọn 2 component | Arranging Objects |
| 7 | Một Comment Text trên sơ đồ, đang chọn và đang sửa | Comment Text |
| 8 | Chuột phải net ▸ **Signal Visibility...** | Signal Display Control |
| 9 | Một Title Block trên sơ đồ | Title Block |
| 10 | Object Tip khi rê chuột lên component, net, PortIO | Object Tips |
| 11 | Edit Appearance của **net** và của **frame**, bấm mở bảng màu | Edit Appearance |
| 12 | Khung Diagram Browser của Block Diagram, mở rộng hết các nhánh Structure Navigator và Content | Diagram Browser |
| 13 | Tab Signals Table của Block Diagram (đủ các cột), menu chuột phải trên bảng | Signals Table |
| 14 | Một **block** trên sơ đồ (khác component) và menu chuột phải của nó | Instantiating a Block |
| 15 | Add ▸ External IP (dialog) | External HDL |
| 16 | Chuột phải component ▸ Update ▸ ... (submenu và dialog Update Interface) | Update Interface |
| 17 | Object Properties của một **block** (mọi trang) | Blocks Page |
| 18 | Object Properties của **embedded block** (mọi trang) và menu chuột phải | Embedded Blocks Page |
| 19 | Object Properties của **signal**: các trang Text Visibility, Attributes, Comments, Appearance | Signals Page |
| 20 | Object Properties ▸ **User Declarations** | User Declarations |
| 21 | Diagram ▸ Add Hierarchy / Remove Hierarchy (dialog) | Design Hierarchy |
| 22 | Một bus có **ripper** trên sơ đồ, đang chọn, và Object Properties của ripper | Ripping From a Bus |
| 23 | Một **global connector** trên sơ đồ | Global Connector |
| 24 | Một component có **Port Map Frame** bật (trên sơ đồ) và dialog Port Map Settings | Port Map Frame |
| 25 | Chuột phải component ▸ Shape ▸ (submenu) và một component đã đổi shape | Logic Shape |
| 26 | Options ▸ Master Preferences ▸ **Block Diagram / Structural Diagram** (mọi trang) | Master Preferences |
| 27 | Mở view **symbol** của một component: Symbol view và Tabular IO view, menu chuột phải | Component Interface |

Ngoài danh sách trên, các mục ✅ vẫn nên được đối chiếu lại bằng mắt với HDS khi anh/chị kiểm tra từng mục.
