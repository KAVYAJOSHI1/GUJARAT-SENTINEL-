# SENTINEL Gujarat Police Innovation Hackathon 2026

## 4-Day End-to-End Product Development Roadmap

### Product Vision

Build a working, modular, vendor-neutral CCTV intelligence platform that
consumes the Government-provided Sentinel camera feeds, performs
real-time video analytics, identifies vehicles through ANPR/OCR, tracks
their movement across cameras, correlates detections with a
representative watchlist, generates alerts, stores searchable
events/evidence, visualizes movement on GIS, and presents a credible
architecture for statewide expansion to approximately 80,000 cameras.

------------------------------------------------------------------------

# 1. Hackathon Alignment

## Reference Architecture Choice

The recommended submission is a **Hybrid Architecture** combining the
useful parts of the five reference models:

-   **Model 1 --- Registry & GIS Foundation**
    -   Central camera registry
    -   GIS mapping
    -   Metadata
    -   Camera health
    -   Department/ownership information
-   **Model 2 --- Unified Viewing & Analytics**
    -   Centralized live viewing
    -   AI analytics
    -   Event visualization
    -   Unified operator dashboard
-   **Model 3 --- VMS Federation & Middleware**
    -   Adapter-based integration
    -   Vendor/VMS neutrality
    -   RTSP/WebRTC/HLS handling
    -   Future VMS connectors
-   **Model 4 --- Central VMS & AI Platform**
    -   Central event intelligence
    -   AI processing
    -   Watchlist correlation
    -   Alerting
    -   Search and investigation
-   **Model 5 --- Hybrid / Innovative Architecture**
    -   Regional gateways
    -   Edge AI
    -   Distributed AI workers
    -   Event-driven architecture
    -   Bandwidth optimization
    -   Statewide scalability

The 4-day PoC does not need to physically implement every statewide
component. It should implement the core pipeline while keeping the
architecture modular enough to scale.

------------------------------------------------------------------------

# 2. Mandatory End-to-End Demonstration

The central demonstration should be:

``` text
Government Camera Catalogue
        |
        v
/api/ingest
        |
        v
Camera Registry
        |
        v
RTSP / TCP
        |
        v
Live Video Frames
        |
        v
Vehicle Detection
        |
        v
Vehicle Tracking
        |
        v
License Plate Detection
        |
        v
OCR / ANPR
        |
        v
Vehicle Registration Number
        |
        v
Event Engine
        |
        +--------------------+
        |                    |
        v                    v
Vehicle History         Watchlist
        |                    |
        v                    v
Cross-Camera GIS       Alert Engine
        |                    |
        +---------+----------+
                  |
                  v
        Investigation Dashboard
```

The evaluator provides a designated vehicle registration number. The
system must be able to search for that vehicle, show its detections
across integrated cameras, provide timestamps and locations, reconstruct
its movement history, visualize it on GIS, and demonstrate watchlist
matching and automated alerts.

------------------------------------------------------------------------

# 3. Government Feed Integration

## 3.1 Camera Catalogue

Start from the Government-provided catalogue rather than hard-coding
camera URLs.

Expected catalogue information includes:

-   Camera ID
-   Location
-   Codec
-   Live status
-   Stream properties
-   RTSP URL
-   WebRTC/WHEP URL
-   HLS URL

Conceptually:

``` text
/api/ingest
      |
      v
Camera Catalogue
      |
      +--> Camera ID
      +--> Location
      +--> Codec
      +--> Status
      +--> RTSP
      +--> WebRTC
      +--> HLS
```

## 3.2 Protocol Usage

``` text
RTSP       -> AI/backend processing
WebRTC     -> Low-latency browser preview
HLS        -> Browser/mobile playback and fallback
```

For AI processing, use **RTSP over TCP**.

## 3.3 Stream Requirements

The ingestion layer must:

-   Force RTSP over TCP
-   Support H.264
-   Support H.265
-   Handle mixed resolutions
-   Avoid assuming a fixed FPS
-   Use PTS timestamps
-   Ignore normal decoder warnings during stream join
-   Reconnect automatically
-   Use exponential backoff
-   Handle feed restarts
-   Handle scene discontinuities
-   Close inactive captures
-   Avoid pulling the stream with curl/wget as if it were a downloadable
    file

Recommended reconnect behavior:

``` text
Failure
  |
  +--> 2 sec
  |
  +--> 4 sec
  |
  +--> 8 sec
  |
  +--> 16 sec
  |
  +--> 30 sec maximum
```

------------------------------------------------------------------------

# 4. Core System Architecture

``` text
                    SENTINEL PLATFORM
                           |
        +------------------+------------------+
        |                  |                  |
        v                  v                  v
 Camera Registry      Stream Manager        GIS
        |                  |                  |
        |                  v                  |
        |             RTSP/TCP               |
        |                  |                  |
        +------------------+------------------+
                           |
                           v
                    AI PROCESSING LAYER
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
      Detection         Tracking          ANPR
          |                |                |
          |                |                v
          |                |               OCR
          +----------------+----------------+
                           |
                           v
                      EVENT ENGINE
                           |
       +-------------------+-------------------+
       |                   |                   |
       v                   v                   v
 Event Database       Watchlist Engine     Evidence
       |                   |                   |
       |                   v                   v
       |                Alerts             Storage
       |
       v
 Cross-Camera Correlation
       |
       v
 Investigation + GIS
       |
       v
 Operator Dashboard
```

------------------------------------------------------------------------

# 5. Technology Stack

## Frontend

-   React.js
-   Leaflet or OpenLayers
-   HTML/CSS/JavaScript
-   WebSocket/SSE for real-time alerts where appropriate

## Backend

-   Python
-   FastAPI
-   REST APIs
-   WebSocket/SSE for live events

## AI

-   YOLO-family pretrained detector
-   ByteTrack or equivalent multi-object tracker
-   License plate detection model
-   PaddleOCR or equivalent OCR
-   Optional vehicle Re-ID model for bonus functionality

## Database

-   PostgreSQL
-   PostGIS

## Evidence/Object Storage

-   S3-compatible object storage or MinIO for PoC
-   Store snapshots/clips separately from relational metadata

## Video

-   FFmpeg
-   OpenCV
-   GStreamer where required
-   NVIDIA DeepStream as an optional optimization path for GPU-heavy
    deployments

## Infrastructure

-   Docker
-   Docker Compose for PoC
-   Kubernetes as a future production orchestration option

------------------------------------------------------------------------

# 6. AI Strategy

## No Training From Scratch

The 4-day solution should use pretrained models.

The core pipeline is:

``` text
Video Frame
    |
    v
YOLO
    |
    v
Vehicle Detection
    |
    v
ByteTrack
    |
    v
Track ID
    |
    v
Plate Detector
    |
    v
Plate Crop
    |
    v
Image Preprocessing
    |
    v
OCR
    |
    v
Vehicle Number
```

Training from scratch is unnecessary for the PoC.

Fine-tuning should only be considered if actual Sentinel footage
produces poor plate detection because of camera angle, resolution,
lighting, or local plate characteristics.

------------------------------------------------------------------------

# 7. Vehicle Detection

Detect:

### Priority 1

-   Car
-   Motorcycle
-   Truck
-   Bus
-   Auto/rickshaw

### Priority 2

-   Person
-   Bicycle
-   Other relevant objects

For every detection:

``` text
camera_id
timestamp
object_type
bounding_box
confidence
track_id
```

------------------------------------------------------------------------

# 8. Vehicle Tracking

Use ByteTrack or another suitable tracker.

Example:

``` text
Frame 1 -> Vehicle #42
Frame 2 -> Vehicle #42
Frame 3 -> Vehicle #42
Frame 4 -> Vehicle #42
```

The tracker creates a temporary identity within the camera.

ANPR then links the visual track to the registration number:

``` text
Track #42
    |
    v
GJ01AB1234
```

Important: camera-local track IDs should not be treated as global
identities.

------------------------------------------------------------------------

# 9. ANPR + OCR

ANPR should identify the license plate region.

OCR reads the characters.

``` text
Vehicle
  |
  v
Plate Detection
  |
  v
Plate Crop
  |
  v
Preprocessing
  |
  v
OCR
  |
  v
GJ01AB1234
```

## Multi-frame confidence strategy

Do not trust one OCR frame.

``` text
Frame 1 -> GJ01AB1234
Frame 2 -> GJ01AB1234
Frame 3 -> GJ01AB1234
Frame 4 -> GJ01AB1284

        |
        v

Consensus / confidence

        |
        v

GJ01AB1234
```

Store:

-   Raw OCR result
-   Confidence
-   Best plate crop
-   Final normalized registration number

Normalize common OCR errors carefully and retain the original evidence.

------------------------------------------------------------------------

# 10. Event Engine

Every meaningful AI detection becomes an event.

Example:

``` json
{
  "event_id": "EVT-82931",
  "camera_id": "CAM-017",
  "plate_number": "GJ01AB1234",
  "vehicle_type": "car",
  "timestamp": "2026-09-01T10:32:14",
  "latitude": 23.03,
  "longitude": 72.58,
  "confidence": 0.94,
  "evidence_reference": "evidence/EVT-82931.jpg"
}
```

The event engine is the central abstraction connecting AI output to the
rest of the system.

------------------------------------------------------------------------

# 11. Cross-Camera Vehicle Intelligence

This is the primary hero feature.

Search:

``` text
GJ01AB1234
```

Return:

``` text
10:02:14 -> CAM-007
10:09:31 -> CAM-013
10:18:07 -> CAM-021
10:31:22 -> CAM-034
```

Generate:

-   First seen
-   Last seen
-   Total sightings
-   Cameras visited
-   Timestamped history
-   Location history
-   Evidence
-   GIS route
-   Watchlist status
-   Alerts

------------------------------------------------------------------------

# 12. Cross-Camera Correlation

Primary method:

``` text
License Plate Number
        |
        v
Normalized registration number
        |
        v
Search event index
        |
        v
Chronologically ordered sightings
        |
        v
Movement history
```

Optional secondary method:

``` text
Plate unavailable
      |
      v
Vehicle Re-ID
      |
      v
Appearance similarity
      |
      v
Probable cross-camera correlation
```

Vehicle Re-ID should be treated as a probabilistic supporting signal,
not definitive identification.

------------------------------------------------------------------------

# 13. GIS Intelligence

Use PostGIS to store camera coordinates and event locations.

Map layers:

-   Cameras
-   Online/offline status
-   Vehicle sightings
-   Alerts
-   Route
-   Department
-   Coverage

Example:

``` text
CAM-007 ●
       \
        ● CAM-013
               \
                ● CAM-021
                       \
                        ● CAM-034
```

Clicking a point shows:

``` text
Camera: CAM-021
Time: 10:18:07
Vehicle: GJ01AB1234
Confidence: 96%
Evidence: Snapshot
```

------------------------------------------------------------------------

# 14. Watchlist System

The official demonstration permits participants to use their own
representative watchlist.

Create a safe representative dataset.

Example:

``` text
plate_number | category          | priority
-------------|-------------------|----------
GJ01AB1234   | Stolen Vehicle    | CRITICAL
GJ05XX7821   | Wanted Vehicle    | HIGH
GJ18KL9090   | Blacklisted       | HIGH
```

Possible categories:

-   Stolen vehicle
-   Wanted vehicle
-   Blacklisted vehicle
-   Suspect watchlist
-   Other authorized demonstration categories

Do not claim that this is a live VAHAN/eGujCop/AFIS/NAFIS integration
unless actual authorized access is provided.

------------------------------------------------------------------------

# 15. Real-Time Alert Engine

Every new ANPR event is checked against the watchlist.

``` text
ANPR
 |
 v
GJ01AB1234
 |
 v
Watchlist Lookup
 |
 +---- No Match ----> Normal Event
 |
 +---- Match -------> Alert Engine
                         |
                         v
                    Critical Alert
```

Alert example:

``` text
CRITICAL WATCHLIST MATCH

Vehicle: GJ01AB1234
Category: Stolen Vehicle
Camera: CAM-021
Location: Ahmedabad
Time: 10:18:07
Confidence: 96%

[VIEW EVIDENCE]
[TRACK VEHICLE]
[VIEW MAP]
[ACKNOWLEDGE]
```

------------------------------------------------------------------------

# 16. Evidence Management

Store evidence separately from relational metadata.

## PostgreSQL

Store:

-   Event ID
-   Camera ID
-   Timestamp
-   Plate
-   Confidence
-   Location
-   Evidence reference

## Object Storage

Store:

-   Plate crop
-   Vehicle snapshot
-   Alert snapshot
-   Optional short clip/reference

Architecture:

``` text
AI Event
   |
   +----> PostgreSQL
   |
   +----> Object Storage
```

Do not store large raw video blobs inside PostgreSQL.

------------------------------------------------------------------------

# 17. Investigation Interface

Create a vehicle investigation page.

``` text
VEHICLE SEARCH

[GJ01AB1234] [SEARCH]
```

Vehicle profile:

``` text
Vehicle: GJ01AB1234
First Seen: 10:02
Last Seen: 10:31
Sightings: 4
Cameras: 4
Alerts: 1
```

Tabs:

-   Timeline
-   GIS Map
-   Evidence
-   Alerts
-   Camera sightings

------------------------------------------------------------------------

# 18. Camera Health Monitoring

Monitor:

-   Online/offline
-   Last frame
-   Last heartbeat
-   Reconnection count
-   Stream errors
-   Codec
-   Resolution
-   Availability

Example:

``` text
CAM-001  Online
CAM-002  Online
CAM-003  Reconnecting
CAM-004  Offline
```

This supports operational monitoring and a bonus evaluation area.

------------------------------------------------------------------------

# 19. Unified Live Dashboard

Main dashboard should contain:

``` text
+------------------------------------------------+
| SENTINEL COMMAND DASHBOARD                     |
+------------------------------------------------+
| Cameras Online | Active Alerts | Vehicles     |
+------------------------------------------------+
|                                                |
|                  GIS MAP                       |
|                                                |
+----------------------+-------------------------+
| LIVE CAMERA GRID     | ALERTS                  |
| CAM-001 | CAM-002    | CRITICAL: GJ01AB1234   |
| CAM-003 | CAM-004    | HIGH: GJ05XX7821       |
+----------------------+-------------------------+
| RECENT VEHICLE EVENTS                         |
+------------------------------------------------+
```

------------------------------------------------------------------------

# 20. Security Architecture

Use:

``` text
User
 |
 v
HTTPS
 |
 v
Authentication
 |
 v
JWT
 |
 v
RBAC
 |
 v
API Layer
 |
 v
Services
 |
 v
Database
```

Implement:

-   HTTPS/TLS
-   JWT authentication
-   Role-based access control
-   Department-level permissions
-   Secure secret management
-   Input validation
-   API authorization
-   Audit logs
-   Encryption at rest where practical
-   Network segmentation in production

------------------------------------------------------------------------

# 21. Roles and Permissions

Example:

### Administrator

-   Manage users
-   Manage departments
-   Manage cameras
-   Manage watchlists
-   System configuration

### Police/Investigator

-   View authorized cameras
-   Search vehicles
-   View alerts
-   View evidence
-   Track vehicle

### Analyst

-   Analytics
-   Reports
-   Historical events
-   GIS investigation

### Viewer

-   Restricted viewing access

------------------------------------------------------------------------

# 22. Audit Logs

Record sensitive actions:

``` text
User: user_102
Action: Vehicle Search
Vehicle: GJ01AB1234
Time: 10:32:41
```

Audit:

-   Login
-   Logout
-   Vehicle searches
-   Evidence access
-   Alert acknowledgement
-   Watchlist changes
-   Camera configuration
-   User changes

------------------------------------------------------------------------

# 23. Government Database Integration Strategy

The problem statement references systems such as:

-   VAHAN
-   SARTHI
-   eGujCop
-   AFIS
-   NAFIS

For the PoC:

**Do not fabricate live integration.**

Instead build an adapter architecture:

``` text
              SENTINEL
                  |
        +---------+---------+
        |         |         |
        v         v         v
     VAHAN     eGujCop    SARTHI
    Adapter    Adapter    Adapter
        |         |         |
        +---------+---------+
                  |
                  v
          Correlation Engine
                  |
                  v
                Alert
```

Each adapter should have a documented interface.

This allows authorized APIs to be plugged in later without changing the
AI core.

------------------------------------------------------------------------

# 24. VMS Federation / Middleware

Different departments may use different:

-   Camera vendors
-   VMS platforms
-   NVRs
-   Protocols
-   Codecs
-   Storage systems

Use an adapter-based integration layer:

``` text
Vendor A -> Adapter A
Vendor B -> Adapter B
VMS X    -> Adapter X
VMS Y    -> Adapter Y
RTSP     -> Native Adapter
```

All adapters produce a standardized internal representation:

``` text
Standard Camera
      |
      +--> camera_id
      +--> location
      +--> stream
      +--> codec
      +--> status
      +--> capabilities
```

The AI layer remains vendor-neutral.

------------------------------------------------------------------------

# 25. Scalable Production Architecture

The 50-camera PoC should be a smaller deployment of the eventual
architecture.

``` text
                         ~80,000 CAMERAS
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
       REGION A              REGION B              REGION N
          |                     |                     |
    Edge Gateway          Edge Gateway          Edge Gateway
          |                     |                     |
     AI / Filtering        AI / Filtering        AI / Filtering
          |                     |                     |
          +---------------------+---------------------+
                                |
                                v
                         SECURE EVENT BUS
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
          Events            Watchlist            Alerts
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                       CENTRAL DATA PLATFORM
                                |
              +-----------------+-----------------+
              |                 |                 |
              v                 v                 v
             GIS             Search          Dashboard
```

------------------------------------------------------------------------

# 26. Why Edge Processing Matters

Bad statewide architecture:

``` text
80,000 cameras
      |
      v
Full video to central
      |
      v
Central AI
```

Better architecture:

``` text
Camera
  |
  v
Regional/Edge Gateway
  |
  v
AI Processing
  |
  v
Event Metadata + Evidence
  |
  v
Central Platform
```

Instead of continuously transporting all raw video, send relevant events
and evidence where operationally appropriate.

Benefits:

-   Lower bandwidth
-   Lower central GPU load
-   Lower latency
-   Better resilience
-   Regional fault isolation
-   Better low-connectivity operation

------------------------------------------------------------------------

# 27. Horizontal AI Scaling

Do not create one monolithic AI process.

``` text
                    AI WORKER POOL
              +--------+--------+--------+
              |        |        |        |
              v        v        v        v
           GPU-01   GPU-02   GPU-03   GPU-N
              |        |        |        |
              +--------+--------+--------+
                       |
                       v
                  Event Bus
```

When camera volume grows:

``` text
500 cameras     -> add workers
5,000 cameras   -> add workers/regions
80,000 cameras  -> distributed regional + central workers
```

This is horizontal scaling.

------------------------------------------------------------------------

# 28. Event-Driven Architecture

Use an event bus/message queue in the scalable design.

``` text
AI Detection
     |
     v
Event Bus
     |
 +---+---+---+---+
 |   |   |   |   |
 v   v   v   v   v
DB GIS Alert Watch Evidence
```

Possible production technologies:

-   Kafka
-   Redpanda
-   RabbitMQ
-   Cloud-native queues

For the 4-day PoC, use the simplest reliable mechanism that keeps the
architecture modular.

------------------------------------------------------------------------

# 29. Storage Strategy

Do not store every frame forever.

## Hot Storage

Recent events:

-   Fast database
-   Recent evidence
-   Frequently accessed data

## Warm Storage

Older events/evidence:

-   Object storage
-   Less frequently accessed

## Cold Storage

Long-term archive:

-   Low-cost storage
-   Authorized retention

Architecture:

``` text
              EVENTS
                |
        +-------+-------+
        |       |       |
        v       v       v
       HOT     WARM    COLD
       SSD    Object   Archive
```

PostgreSQL/PostGIS should store metadata, not entire video archives.

------------------------------------------------------------------------

# 30. Database Design

## Camera

``` text
camera_id
department_id
name
latitude
longitude
vendor
vms
codec
resolution
stream_type
status
last_seen
```

## Vehicle Event

``` text
event_id
camera_id
timestamp
plate_number
vehicle_type
confidence
latitude
longitude
track_id
evidence_reference
```

## Watchlist

``` text
watchlist_id
plate_number
category
priority
status
reference_id
created_at
```

## Alert

``` text
alert_id
event_id
alert_type
severity
status
created_at
acknowledged_by
```

## Audit Log

``` text
audit_id
user_id
action
resource
timestamp
metadata
```

Use PostGIS for spatial queries.

------------------------------------------------------------------------

# 31. Search Architecture

At PoC scale:

``` text
React
  |
  v
FastAPI
  |
  v
PostgreSQL
```

At larger scale:

``` text
Search API
    |
    +--> PostgreSQL/PostGIS
    |
    +--> Dedicated Search Index if required
```

Potential production search technologies:

-   OpenSearch
-   Elasticsearch
-   PostgreSQL indexes

Start simple and scale only when event volume requires it.

------------------------------------------------------------------------

# 32. Infrastructure Sizing Strategy

Do not claim a fixed production hardware number without real stream
properties.

Sizing depends on:

-   Resolution
-   Codec
-   FPS
-   Bitrate
-   Analytics frequency
-   Number of simultaneous streams
-   GPU model
-   Model complexity
-   Edge vs central processing

For the PoC:

``` text
~50 feeds
    |
    v
Stream/AI workers
    |
    v
GPU-capable machine(s)
    |
    v
PostgreSQL/PostGIS
    |
    v
Frontend
```

For production, benchmark the exact models and stream characteristics
before final procurement.

------------------------------------------------------------------------

# 33. Network Planning

Per-camera bandwidth varies with codec, resolution, FPS and bitrate.

Do not assume a single bitrate for all cameras.

Use:

``` text
Total bandwidth
=
sum of active stream bitrates
+
protocol/network overhead
```

Edge processing reduces central bandwidth because:

``` text
Raw video
   |
   v
Edge AI
   |
   v
Events + evidence
   |
   v
Central
```

------------------------------------------------------------------------

# 34. High Availability

Production architecture:

``` text
                 Load Balancer
                       |
              +--------+--------+
              |                 |
              v                 v
          Service A          Service B
              |                 |
              +--------+--------+
                       |
                       v
                 DB Primary
                       |
                       v
                 DB Replica
```

Use:

-   Redundant services
-   Database replication
-   Object storage replication
-   Health checks
-   Automatic service restart
-   Regional redundancy
-   Backups

------------------------------------------------------------------------

# 35. Disaster Recovery

Plan:

``` text
Primary Region
      |
      +--> Database Backup
      +--> Object Backup
      +--> Configuration Backup
      |
      v
Secondary/DR Region
```

Define:

-   RPO
-   RTO
-   Backup frequency
-   Restore procedure
-   Regional failover

Exact production values should be agreed with the deployment authority
and retention/security policy.

------------------------------------------------------------------------

# 36. Monitoring and Observability

Monitor:

### Cameras

-   Online/offline
-   Stream latency
-   Frame reception
-   Reconnects

### AI

-   GPU utilization
-   FPS processed
-   Inference latency
-   Queue depth
-   Detection counts
-   ANPR confidence

### Backend

-   API latency
-   Errors
-   Database connections
-   Event throughput

### Infrastructure

-   CPU
-   Memory
-   Disk
-   Network
-   GPU
-   Storage

Architecture:

``` text
Services
   |
   +--> Logs
   +--> Metrics
   +--> Health Checks
   +--> Alerts
```

------------------------------------------------------------------------

# 37. Four-Day Development Roadmap

# DAY 1 --- FOUNDATION

## Objective

**Government feed -\> working frame -\> first AI detection**

### Tasks

1.  Read `/api/ingest`
2.  Build camera catalogue parser
3.  Store camera metadata
4.  Build RTSP/TCP connector
5.  Test H.264
6.  Test H.265
7.  Implement reconnect
8.  Implement PTS-based timing
9.  Build basic backend
10. Build PostgreSQL schema
11. Build React shell
12. Display one live feed
13. Run pretrained YOLO
14. Detect vehicles
15. Create basic camera map

### End-of-Day Test

``` text
Government Camera
      |
      v
RTSP/TCP
      |
      v
Frame
      |
      v
YOLO
      |
      v
Vehicle Detected
```

Do not proceed until this works reliably.

------------------------------------------------------------------------

# DAY 2 --- VEHICLE INTELLIGENCE

## Objective

**Vehicle -\> Plate -\> Event -\> Database**

### Tasks

1.  Integrate tracker
2.  Assign track IDs
3.  Add plate detection
4.  Add OCR
5.  Add plate preprocessing
6.  Add multi-frame consensus
7.  Normalize plate numbers
8.  Create vehicle-event API
9.  Store events
10. Store evidence snapshots
11. Build vehicle search
12. Build event timeline
13. Test multiple cameras

### End-of-Day Test

``` text
Vehicle
  |
  v
Track
  |
  v
Plate
  |
  v
GJ01AB1234
  |
  v
Event Database
```

------------------------------------------------------------------------

# DAY 3 --- HERO DEMONSTRATION

## Objective

**Trace vehicle -\> GIS -\> Watchlist -\> Alert**

### Tasks

1.  Cross-camera vehicle search
2.  Chronological movement history
3.  GIS route
4.  Watchlist database
5.  Watchlist matching
6.  Real-time alert engine
7.  Alert priority
8.  Evidence viewer
9.  Investigation page
10. Vehicle profile
11. Camera health dashboard
12. Live dashboard integration
13. Government feed testing
14. Own-feed testing

### Target Demonstration

``` text
GJ01AB1234
      |
      v
CAM-007
      |
      v
CAM-013
      |
      v
CAM-021
      |
      v
CAM-034
      |
      +--> GIS Route
      |
      +--> Timeline
      |
      +--> Evidence
      |
      +--> Watchlist Match
              |
              v
         CRITICAL ALERT
```

This is the most important day.

------------------------------------------------------------------------

# DAY 4 --- HARDENING + SUBMISSION

## Objective

**Make the system reliable, demonstrable and submission-ready.**

### Technical

1.  Test Government cameras
2.  Test H.264/H.265
3.  Test reconnect
4.  Test camera failure
5.  Test multiple streams
6.  Test ANPR accuracy
7.  Test watchlist matching
8.  Test GIS route
9.  Test vehicle search
10. Fix UI/API bugs
11. Improve latency
12. Add authentication
13. Add RBAC if stable
14. Add audit logging if stable
15. Dockerize system
16. Create reproducible startup process

### Documentation

Complete:

-   PPT/PDF
-   HLD
-   Architecture diagrams
-   Integration strategy
-   AI architecture
-   Cybersecurity architecture
-   Deployment architecture
-   Infrastructure sizing
-   Network/bandwidth strategy
-   Storage/retention strategy
-   AI processing capacity
-   HA/DR
-   Cost-benefit analysis
-   Department information requirements
-   Scalability strategy
-   Future roadmap

### Demonstration

Record:

1.  Own-feed demonstration
2.  Government-feed demonstration
3.  Vehicle tracking demonstration
4.  Watchlist alert demonstration
5.  Output report

------------------------------------------------------------------------

# 38. Final Feature Priorities

## P0 --- Mandatory / Core

``` text
1. Government feed onboarding
2. RTSP/TCP ingestion
3. Live viewing
4. Vehicle detection
5. Vehicle tracking
6. ANPR
7. OCR
8. Vehicle events
9. Vehicle search
10. Cross-camera history
11. GIS route
12. Watchlist
13. Real-time alerts
14. Evidence
15. Government-feed demonstration
16. Output report
```

## P1 --- Strong Enhancements

``` text
17. Camera health
18. RBAC
19. Audit logs
20. Investigation dashboard
21. Alert prioritization
22. API layer
23. H.264/H.265 handling
24. Automatic reconnect
25. Analytics dashboard
```

## P2 --- Bonus

``` text
26. Vehicle Re-ID
27. Person detection
28. Intrusion detection
29. Anomaly detection
30. Edge AI demonstration
31. Advanced incident reports
32. Advanced operational analytics
```

Do not allow P2 features to compromise P0 reliability.

------------------------------------------------------------------------

# 39. Problems and Technical Challenges

## Challenge 1 --- Heterogeneous Streams

Different:

-   Codecs
-   Resolutions
-   FPS
-   Vendors
-   VMS platforms

Solution:

**Adapter-based stream abstraction + per-camera configuration.**

------------------------------------------------------------------------

## Challenge 2 --- RTSP Reliability

Streams may disconnect.

Solution:

-   TCP
-   Exponential backoff
-   Health monitoring
-   Reconnect state machine
-   Non-fatal decoder warnings

------------------------------------------------------------------------

## Challenge 3 --- Incorrect Timing

Arrival time is not equivalent to video time.

Solution:

**Use PTS timestamps.**

Never derive speed/movement timing from assumed FPS.

------------------------------------------------------------------------

## Challenge 4 --- ANPR Errors

Possible causes:

-   Low resolution
-   Motion blur
-   Bad lighting
-   Occlusion
-   Angle
-   Plate size

Solution:

-   Plate detector
-   Preprocessing
-   Multiple frames
-   OCR consensus
-   Confidence thresholds
-   Evidence retention

------------------------------------------------------------------------

## Challenge 5 --- Cross-Camera Identity

A track ID from Camera A cannot automatically equal a track ID from
Camera B.

Solution:

Primary:

**Plate-based correlation**

Optional:

**Vehicle Re-ID + temporal/spatial reasoning**

------------------------------------------------------------------------

## Challenge 6 --- Bandwidth

Sending every raw stream centrally becomes expensive.

Solution:

**Regional/edge processing + event-based central transmission.**

------------------------------------------------------------------------

## Challenge 7 --- Database Growth

Millions of events can accumulate.

Solution:

-   Store metadata rather than raw video in PostgreSQL
-   Partition event data
-   Index plate/timestamp/camera
-   PostGIS spatial indexing
-   Object storage for evidence
-   Retention policies
-   Hot/warm/cold storage

------------------------------------------------------------------------

## Challenge 8 --- GPU Capacity

AI workloads scale with:

-   Camera count
-   FPS
-   Model complexity
-   Resolution

Solution:

**GPU worker pool + batching where appropriate + edge processing +
horizontal scaling.**

------------------------------------------------------------------------

## Challenge 9 --- Government Database Availability

Real systems may require authorization and API contracts.

Solution:

**Adapter architecture + representative watchlist for PoC.**

Never fabricate live access.

------------------------------------------------------------------------

## Challenge 10 --- 80,000-Camera Scaling

A single-server architecture will not scale.

Solution:

``` text
Cameras
  |
Regional Gateways
  |
Edge AI
  |
Event Bus
  |
Distributed Services
  |
Central Intelligence
```

------------------------------------------------------------------------

# 40. Cost-Benefit Strategy

The proposal should emphasize reuse of existing infrastructure.

## Cost reduction

-   Existing cameras reused
-   Existing VMS infrastructure federated
-   Edge analytics reduces bandwidth
-   Event-based storage reduces storage consumption
-   Open standards reduce vendor lock-in
-   Modular adapters reduce replacement costs

## Operational benefits

-   Unified visibility
-   Faster vehicle tracing
-   Automated watchlist alerts
-   Searchable evidence
-   Central GIS intelligence
-   Better camera health visibility
-   Faster investigation
-   Future integration readiness

------------------------------------------------------------------------

# 41. Department-Wise Information Requirements

For every department, collect:

### Camera

-   Camera ID
-   Location
-   GPS
-   Type
-   Vendor
-   Model
-   Resolution
-   Codec
-   FPS
-   Bitrate
-   Night capability
-   PTZ capability

### Network

-   Connectivity
-   IP/routing information
-   Bandwidth
-   Firewall/NAT
-   VPN
-   Availability

### VMS/NVR

-   VMS vendor
-   Version
-   NVR details
-   Protocol support
-   API availability
-   Existing licenses
-   AMC status

### Storage

-   Storage type
-   Retention
-   Capacity
-   Cloud/local
-   Backup
-   Export capabilities

### Governance

-   Ownership
-   Department
-   Authorized users
-   Data-sharing policy
-   Retention policy
-   Security requirements

------------------------------------------------------------------------

# 42. Statewide Rollout Strategy

## Phase 1 --- PoC

``` text
~50 cameras
Single deployment
Core AI
GIS
ANPR
Watchlist
Alerts
```

## Phase 2 --- Pilot

``` text
500–1,000 cameras
Regional gateway
Multiple AI workers
Health monitoring
```

## Phase 3 --- Regional

``` text
5,000–10,000 cameras
Edge processing
Distributed event architecture
Regional HA
```

## Phase 4 --- Statewide

``` text
~80,000 cameras
Multi-region
Edge + central intelligence
Distributed AI
Event bus
HA/DR
Central GIS
Department integrations
```

------------------------------------------------------------------------

# 43. Future Roadmap

After the PoC:

### Phase A

-   Improve ANPR accuracy
-   Improve camera onboarding
-   Improve dashboard
-   Add RBAC
-   Add audit

### Phase B

-   Edge AI
-   Vehicle Re-ID
-   More analytics
-   VMS adapters
-   Authorized database connectors

### Phase C

-   Regional deployments
-   GPU clusters
-   Event streaming
-   HA/DR
-   Search infrastructure

### Phase D

-   Statewide deployment
-   \~80,000 cameras
-   Advanced analytics
-   Automated incident workflows
-   Interdepartmental intelligence

------------------------------------------------------------------------

# 44. Final Product Workflow

``` text
                 GOVERNMENT CCTV GRID
                         |
                         v
                  CAMERA CATALOGUE
                         |
                         v
                  CAMERA REGISTRY
                         |
                         v
                   STREAM MANAGER
                         |
                     RTSP/TCP
                         |
                         v
                  VIDEO PROCESSING
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       Vehicle         Person         Other
      Detection       Detection      Analytics
          |
          v
       Tracking
          |
          v
    Plate Detection
          |
          v
         OCR
          |
          v
   Vehicle Registration
          |
          v
     EVENT ENGINE
          |
    +-----+-----+----------------+
    |           |                |
    v           v                v
Database    Watchlist         Evidence
    |           |                |
    |           v                |
    |        Alert Engine        |
    |           |                |
    +-----------+----------------+
                |
                v
      CROSS-CAMERA CORRELATION
                |
        +-------+-------+
        |               |
        v               v
       GIS          Investigation
        |               |
        +-------+-------+
                |
                v
        SENTINEL DASHBOARD
```

------------------------------------------------------------------------

# 45. The Core Demo Story

The final demo should tell one continuous story.

### Step 1

Show the Government camera catalogue.

### Step 2

Onboard cameras automatically.

### Step 3

Show live camera feeds.

### Step 4

Show vehicle detection.

### Step 5

Show ANPR reading:

``` text
GJ01AB1234
```

### Step 6

Search that registration number.

### Step 7

Show:

``` text
CAM-007 -> CAM-013 -> CAM-021 -> CAM-034
```

### Step 8

Show the route on GIS.

### Step 9

Show evidence for each sighting.

### Step 10

Show watchlist match.

### Step 11

Generate:

``` text
CRITICAL WATCHLIST ALERT
```

### Step 12

Open the investigation page and show the complete vehicle history.

This single workflow demonstrates the majority of the mandatory
requirements.

------------------------------------------------------------------------

# 46. What Must Be Real

The working PoC should genuinely implement:

-   Government feed consumption
-   Camera onboarding
-   RTSP connection
-   Live video
-   Vehicle detection
-   Vehicle tracking
-   ANPR
-   OCR
-   Event storage
-   Vehicle search
-   Cross-camera history
-   GIS visualization
-   Watchlist matching
-   Real-time alerts
-   Evidence snapshots
-   Government-feed demonstration

------------------------------------------------------------------------

# 47. What Can Be Representative

It is acceptable to use representative data for the demonstration where
the problem statement permits it, especially:

-   Watchlist records
-   Stolen vehicle records
-   Wanted vehicle records
-   Blacklisted vehicle records

Government-system adapters such as VAHAN/eGujCop/SARTHI/AFIS/NAFIS
should be presented as integration-ready interfaces unless authorized
live APIs are supplied.

------------------------------------------------------------------------

# 48. Final Architecture Principle

The entire product should follow one central principle:

> **Do not build a monolithic CCTV application. Build a modular
> intelligence platform where camera integration, AI processing, event
> generation, watchlist correlation, GIS, evidence, alerts and user
> interfaces are independently scalable services.**

The 50-camera PoC is simply the first deployment of the architecture.

``` text
50 Cameras
    |
    v
Working PoC
    |
    v
500 Cameras
    |
    v
Regional Pilot
    |
    v
5,000+ Cameras
    |
    v
Distributed Regional Platform
    |
    v
~80,000 Cameras
```

## Ultimate Value Proposition

**Sentinel converts fragmented CCTV infrastructure into a unified,
searchable, GIS-aware intelligence network.**

``` text
CAMERAS
   ↓
VIDEO
   ↓
AI
   ↓
VEHICLES / PLATES
   ↓
EVENTS
   ↓
CROSS-CAMERA INTELLIGENCE
   ↓
GIS
   ↓
WATCHLIST
   ↓
REAL-TIME ALERTS
   ↓
INVESTIGATION
```

The 4-day objective is not to implement the entire statewide system. The
objective is to build a **fully functional, credible vertical slice of
the statewide architecture** and demonstrate that the same modular
design can scale from approximately 50 evaluation cameras toward
approximately 80,000 cameras.
