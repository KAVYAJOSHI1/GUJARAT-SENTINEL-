# Gujarat Sentinel Camera GIS Metadata Documentation

This document records the application-side GIS coordinate enrichment for the Gujarat Sentinel CCTV Sandbox grid (30 cameras).

> [!IMPORTANT]
> **Source Attribution Notice**:
> - Sentinel's official camera catalogue (`https://cctv.corp8.cloud/cameras.json`) provides **only** camera `id` and `name`.
> - Geographic coordinates (`latitude`, `longitude`) are **NOT** supplied by Sentinel.
> - All coordinates in this documentation and `data/camera_registry.json` are application-enriched GIS metadata (`location_source: "application_geocoding"`).

---

## 1. Camera Registry GIS Matrix

| Camera | Original Name | Latitude | Longitude | City | District | Confidence | Source | Verified |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `cam01` | 01 Chiman bhai Bridge | 23.069362 | 72.587224 | Ahmedabad | Ahmedabad | HIGH | application_geocoding | true |
| `cam02` | 02 Janpath | 23.029815 | 72.571432 | Ahmedabad | Ahmedabad | HIGH | application_geocoding | true |
| `cam03` | 03 O.N.G.C. Office | 23.111800 | 72.585500 | Ahmedabad | Ahmedabad | HIGH | application_geocoding | true |
| `cam04` | 04 Paldi Circle | 23.012580 | 72.564120 | Ahmedabad | Ahmedabad | HIGH | application_geocoding | true |
| `cam05` | 05 Visat teen Rasta | 23.115700 | 72.581500 | Ahmedabad | Ahmedabad | HIGH | application_geocoding | true |
| `cam06` | 06 Timbavadi gate-Junagadh | 21.503307 | 70.433500 | Junagadh | Junagadh | HIGH | application_geocoding | true |
| `cam07` | 07 hero-showroom-gir-somnath | 20.910110 | 70.365279 | Veraval | Gir Somnath | MEDIUM | application_geocoding | false |
| `cam08` | 08 majewadi-gate-junagadh | 21.535478 | 70.460007 | Junagadh | Junagadh | HIGH | application_geocoding | true |
| `cam09` | 09 new-bypass-near-by-circle-junagadh-2 | 21.586345 | 70.447325 | Junagadh | Junagadh | MEDIUM | application_geocoding | false |
| `cam10` | 10 char-chowk-road-2-junagadh | 21.522450 | 70.457810 | Junagadh | Junagadh | MEDIUM | application_geocoding | false |
| `cam11` | 11 dolatpara-junagadh | 21.558757 | 70.465922 | Junagadh | Junagadh | HIGH | application_geocoding | true |
| `cam12` | 12 Tri Mandir Adalaj Tollnaka | 23.178482 | 72.572128 | Gandhinagar | Gandhinagar | HIGH | application_geocoding | true |
| `cam13` | 13 CN Vidhyalaya | 23.018995 | 72.548889 | Ahmedabad | Ahmedabad | HIGH | application_geocoding | true |
| `cam14` | 14 Delight RLVD | 23.024510 | 72.556230 | Ahmedabad | Ahmedabad | MEDIUM | application_geocoding | false |
| `cam15` | 15 Suvidha park | 23.003420 | 72.559810 | Ahmedabad | Ahmedabad | MEDIUM | application_geocoding | false |
| `cam16` | 16 Visat P2 | 23.116200 | 72.582000 | Ahmedabad | Ahmedabad | HIGH | application_geocoding | true |
| `cam17` | 17 Rajkot Bus Port CCTV | 22.292150 | 70.799480 | Rajkot | Rajkot | HIGH | application_geocoding | true |
| `cam18` | 18 Rajkot CCTV | 22.305326 | 70.802838 | Rajkot | Rajkot | MEDIUM | application_geocoding | false |
| `cam19` | 19 KHAPARIA GRAM PANCHAYAT , TALUKA GANDEVI, DISTRICT NAVSARI | 20.863404 | 73.048965 | Gandevi | Navsari | HIGH | application_geocoding | true |
| `cam20` | 20 Mohanpura | 23.598210 | 72.964520 | Himatnagar | Sabarkantha | MEDIUM | application_geocoding | false |
| `cam21` | 23 Patan Dethali Char Rasta | 23.916615 | 72.361147 | Patan | Patan | HIGH | application_geocoding | true |
| `cam22` | 28 BK Mervada tran Rasta | 24.238410 | 72.185200 | Palanpur | Banaskantha | MEDIUM | application_geocoding | false |
| `cam23` | 30 kheram | 20.655820 | 73.087450 | Khergam | Navsari | MEDIUM | application_geocoding | false |
| `cam24` | 33 dehgam | 23.164033 | 72.881832 | Dehgam | Gandhinagar | HIGH | application_geocoding | true |
| `cam25` | 34 dhanori | 20.838862 | 73.023955 | Gandevi | Navsari | HIGH | application_geocoding | true |
| `cam26` | 35 TANKAL | 20.860591 | 73.130617 | Chikhli | Navsari | HIGH | application_geocoding | true |
| `cam27` | 36 bilimora | 20.767169 | 72.969345 | Bilimora | Navsari | HIGH | application_geocoding | true |
| `cam28` | 37 bilimora | 20.766008 | 73.007151 | Bilimora | Navsari | HIGH | application_geocoding | true |
| `cam29` | 38 bilimora | 20.758410 | 72.956820 | Bilimora | Navsari | MEDIUM | application_geocoding | false |
| `cam30` | Gandhidham Rambaugh p2 | 23.076820 | 70.132150 | Gandhidham | Kutch | HIGH | application_geocoding | true |

---

## 2. Confidence Level Breakdown

- **TOTAL CAMERAS**: `30`
- **HIGH confidence**: `20` (Exact landmarks / intersections confidently matched)
- **MEDIUM confidence**: `10` (Associated with verified road/area, but exact camera pole requires physical audit)
- **LOW confidence**: `0`
- **UNRESOLVED**: `0`

---

## 3. Manual On-Site Physical Verification List

The following 10 cameras are marked `location_verified: false` and are recommended for physical GPS audit by field engineers:

1. `cam07` (`07 hero-showroom-gir-somnath`) — Hero Showroom, Veraval Highway, Gir Somnath
2. `cam09` (`09 new-bypass-near-by-circle-junagadh-2`) — New Bypass Circle 2, NH 151, Junagadh
3. `cam10` (`10 char-chowk-road-2-junagadh`) — Char Chowk Road 2, Diwan Chowk, Junagadh
4. `cam14` (`14 Delight RLVD`) — Delight RLVD Junction, C.G. Road / Ambawadi, Ahmedabad
5. `cam15` (`15 Suvidha park`) — Suvidha Park, Vasna Barrage Road, Ahmedabad
6. `cam18` (`18 Rajkot CCTV`) — Trikon Baug Square, Rajkot
7. `cam20` (`20 Mohanpura`) — Mohanpura Square, Himatnagar, Sabarkantha
8. `cam22` (`28 BK Mervada tran Rasta`) — Mervada Tran Rasta, Palanpur - Deesa Highway, Banaskantha
9. `cam23` (`30 kheram`) — Khergam Tran Rasta, Navsari
10. `cam29` (`38 bilimora`) — Somnath Road Junction, Bilimora, Navsari

---

## 4. Integration Readiness

The registry file `data/camera_registry.json` is fully structured for direct consumption by Vishakha's GIS Map Module and standard GeoJSON / Leaflet / Mapbox frontend components.
