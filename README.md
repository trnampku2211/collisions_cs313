# NYC Motor Vehicle Collisions — DBSCAN Hotspots

Pipeline phục vụ đồ án phát hiện điểm nóng tai nạn giao thông tại NYC bằng DBSCAN. Mô hình dùng khoảng cách Haversine, hỗ trợ gộp tọa độ gần trùng và dùng số vụ tại mỗi vị trí làm `sample_weight`.

## Luồng xử lý

1. Đọc CSV theo chunk và giới hạn giai đoạn 2017–2022.
2. Làm sạch ngày, giờ, số liệu thương vong và tọa độ.
3. Tạo biến thời gian, mức độ nghiêm trọng và giai đoạn phân tích.
4. Gộp tọa độ theo độ chính xác cấu hình.
5. Chạy DBSCAN riêng cho 2017–2019 và 2020–2022.
6. Đánh giá coverage, noise, kích thước cụm và mức độ tập trung.
7. Xuất profile cụm, bảng xếp hạng, biểu đồ và bản đồ HTML.

## Cài đặt

```powershell
python -m pip install -r requirements.txt
```

## Chạy pipeline

```powershell
python main.py run
```

Chạy lại bước đọc và làm sạch, bỏ qua cache:

```powershell
python main.py run --force-refresh
```

Smoke test trên một phần dữ liệu:

```powershell
python main.py run --sample-rows 50000
```

Khảo sát tham số cho một giai đoạn:

```powershell
python main.py tune --period 2017-2019 --sample-locations 30000
```

## Đầu ra

- `outputs/tables/`: location clusters, cluster profiles và bảng tuning.
- `outputs/experiment_results/`: metric JSON của từng lần chạy.
- `outputs/figures/`: biểu đồ top hotspot và k-distance.
- `outputs/maps/`: bản đồ tương tác top hotspot.
- `web/data/`: GeoJSON và `bundle.js` cho ứng dụng Leaflet, được tạo tự động bởi `python main.py run`.

Bản đồ `hotspots_period_comparison.html` đặt hai giai đoạn trên cùng một nền bản đồ. Dùng Layer Control ở góc phải để bật/tắt từng giai đoạn; kích thước vòng tròn biểu diễn số vụ trong cluster.

## Bản đồ Leaflet

Sau khi chạy pipeline, mở trực tiếp `web/index.html`. Ứng dụng nạp dữ liệu từ `web/data/bundle.js` nên không cần local server. Muốn thử chế độ HTTP, có thể chạy từ thư mục project:

```powershell
python -m http.server 8000
```

Mở `http://localhost:8000/web/`. Bản đồ dùng nền vector OpenFreeMap (dữ liệu OpenStreetMap) qua Leaflet và MapLibre, có bộ lọc giai đoạn, số vụ tối thiểu, chỉ cụm có tử vong và cách xếp hạng. Chọn một cụm để xem các tọa độ va chạm có nhiều vụ nhất trong cụm đó. Dữ liệu chi tiết từng vị trí được xuất cho 20 cụm nhiều vụ nhất mỗi giai đoạn, tối đa 1.500 vị trí/cụm; giao diện ghi rõ khi chỉ hiện một phần. Dữ liệu vụ tai nạn lưu trên máy, còn thư viện bản đồ và nền bản đồ cần kết nối mạng khi mở. OpenFreeMap yêu cầu ghi nguồn OpenMapTiles/OpenStreetMap; dòng ghi nguồn nằm ở góc dưới bản đồ.

Trên máy hiện tại, lệnh `python` trong PATH có thể trỏ tới Windows Store alias. Có thể chạy server bằng Python đã dùng để tạo dữ liệu:

```powershell
& 'C:\Users\NamPhu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m http.server 8000
```

Marker đặt tại tọa độ va chạm có thật gần tâm hình học của cụm nhất, không phải một giao lộ chính thức hay ranh giới cụm. Tên đường và cặp đường trong popup được lấy từ các giá trị được ghi nhận nhiều nhất trong dữ liệu crash của chính cụm đó; giao diện chỉ dùng tên đường làm nhãn nếu nó chiếm ít nhất 10% số vụ. Chưa thực hiện map matching với bộ LION chính thức; nên không diễn giải tên đường như vị trí chính xác của mọi vụ trong cụm.

DBSCAN không có cơ chế `predict()` tự nhiên cho điểm mới như K-Means. Project lưu nhãn cụm, tham số và kết quả phân tích thay vì coi object model là mô hình dự báo triển khai.

Cấu hình mặc định dùng chung `eps=100 m` và `min_samples=30` cho hai giai đoạn. Bộ tham số này được chọn từ grid search trên toàn bộ tập vị trí để giảm hiện tượng nhiều khu vực bị nối thành một siêu cụm, đồng thời vẫn giữ coverage đủ lớn để phân tích hotspot.

