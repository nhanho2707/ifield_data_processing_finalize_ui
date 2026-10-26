# Changelog

Các thay đổi của iField Data Processing. Phiên bản mới nhất ở trên cùng.

## [Chưa phát hành] — 2026-10-14

Các thay đổi dưới đây chưa có trong bộ cài `iFieldDataProcessing-Setup-0.1.0.exe`. Riêng mục
"Một câu có nhiều dòng thì lấy dòng cuối" đã có trong bộ cài build ngày 2026-10-13.

### Thêm mới

- **Kiểm tra update_data.csv trước khi chạy.** Bước mới "Kiểm tra update_data.csv" chạy ngay sau bước tạo MDD,
  trước khi nạp dữ liệu. Mỗi dòng được so với file `_EXPORT.mdd`. Các trường hợp báo lỗi:
  - InstanceID trống hoặc không có trong dữ liệu (phiếu test bị loại theo cấu hình được ghi rõ lý do);
  - tên câu không có trong MDD;
  - code không có trong danh sách code của câu (ví dụ `{_5}` khi metadata chỉ có `_1,_2,_3`);
  - giá trị câu chọn code không viết dạng `{_1}` hoặc `{_1,_2}`;
  - câu chọn một mà điền nhiều code, vượt số code tối đa, hoặc một code ghi hai lần;
  - code loại trừ (Không biết, Không trả lời…) đi kèm code khác;
  - câu số mà giá trị không phải số hoặc ngoài khoảng min–max; câu ngày tháng mà giá trị không phải ngày.

  Text dài hơn độ dài tối đa trong MDD chỉ là cảnh báo. Khi có lỗi, quy trình dừng, không nạp và không update gì.
  Danh sách lỗi lưu ở `logs\update_data_check_<thời gian>.xlsx` để lọc và sửa file.
- **Nút "Kiểm tra" trong tab Cấu hình cũng kiểm tra update_data.csv** khi project đã có file `_EXPORT.mdd`,
  nên biết lỗi trước khi chạy cả quy trình.
- **Đổi ngôn ngữ giao diện Tiếng Việt / English** bằng ô chọn ở góc trên bên phải. Áp dụng ngay, giữ nguyên
  project và tab đang mở, và được nhớ cho lần mở sau. Nhật ký và thông báo lỗi vẫn bằng tiếng Anh.
- **ProtoID tự lấy từ tên file XML** (`ProtoSurvey_12319_{…}.xml` → `12319`) trong bảng nguồn dữ liệu:
  - mỗi file XML chưa có trong bảng được tự thêm một dòng;
  - dòng có ProtoID trong CSV được chọn sẵn file XML cùng số;
  - đổi file XML của một dòng thì ProtoID và số dòng CSV đổi theo.
- App nhớ tab đang mở cho lần mở sau.

### Thay đổi

- **Nạp dữ liệu nhanh hơn khoảng 4 lần.** Bước "Nạp dữ liệu phần main" và "Nạp dữ liệu các stage follow-up" không còn đọc
  từng ô qua pandas Series nữa (đây là phần tốn thời gian nhất). Project 939 phiếu × 3794 cột giảm từ ~67 giây xuống
  ~17 giây. Dữ liệu ghi vào DDF giữ nguyên như trước.
- **update_data.csv: một câu có nhiều dòng thì lấy dòng cuối.** Nếu cùng một câu của một InstanceID xuất hiện
  nhiều lần, chỉ dòng dưới cùng được dùng. Tên câu so sánh không phân biệt hoa/thường.
- **Giá trị trong update_data.csv được ghi theo kiểu của câu trong MDD.** Câu chọn code ghi `{_5}` (trước đây bị
  ghi thành chuỗi `'{_5}'`), câu text có nháy, câu số không nháy. Tên câu tự sửa hoa/thường theo MDD.
- **Lỗi khi update vào DDF giờ làm bước "Áp dụng update_data.csv" báo Lỗi**, thay vì chỉ ghi cảnh báo và báo Xong.

### Sửa lỗi

- **Lăn chuột không còn làm đổi giá trị** ở cột File XML, cột Phần và ô Ngôn ngữ mặc định trong tab Cấu hình.
  Muốn đổi phải bấm mở danh sách rồi chọn; lăn chuột chỉ cuộn trang.

### Lưu ý khi soạn update_data.csv

- Giá trị nhiều code có dấu phẩy nên phải nằm trong ngoặc kép, ví dụ `"{_1,_2}"`. Excel tự thêm khi lưu CSV.
- Để trống Current Value để xoá giá trị của câu đó.
