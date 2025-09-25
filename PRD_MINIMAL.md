# Vaya Transport Assistant - Minimal PRD

## Current System (What Exists)

### Architecture
- **Two-Agent System**: Planning Agent + Execution Agent
- **Coordinator**: Manages agent flow and memory persistence
- **State Management**: WorldState blackboard with slots (origin/destination)
- **Memory**: JSON-based conversation persistence

### Current Tools
- **Location**: Geolocate (IP-based), Geocode, ReverseGeocode
- **Transit**: Google Maps Directions (transit/walking)
- **Places**: Places Search, Place Details
- **Weather**: Current conditions via Google API
- **Conversation**: Basic text handling

### Current Capabilities
- CLI interface with colored output
- Real-time location detection
- Public transit directions
- Weather information
- Place searches ("nearest coffee")
- Conversation memory between sessions

## Enhancement Goals

### 1. Twilio Integration
**Goal**: Add SMS/WhatsApp communication channels

**Requirements**:
- Bidirectional SMS messaging
- WhatsApp Business API integration
- Message routing between channels
- Preserve conversation context across channels

**Implementation**:
- Add Twilio SDK to requirements
- Create Communication Agent
- Implement webhook handling
- Add channel-specific formatting

### 2. Stress-Reduction Features
**Goal**: Detect transit delays and provide calming guidance

**Requirements**:
- Monitor real-time transit disruptions
- Trigger calming messages during delays
- Provide CBT-based stress relief techniques
- No personal behavior tracking

**Implementation**:
- Add Wellness Agent to agent architecture
- Integrate transit API feeds for delay detection
- Create intervention content library
- Implement situational stress detection (delay-based, not user-based)

### 3. Enhanced Location Services
**Goal**: Upgrade from IP-based to precise location detection

**Current Limitation**: IP-based geolocation (±1+ mile accuracy)

**Requirements**:
- GPS-based location via mobile devices
- WiFi/Bluetooth beacon triangulation
- Browser geolocation API integration
- Fallback to IP-based when precise location unavailable

**Implementation**:
- Add mobile app capability for GPS access
- Integrate HTML5 geolocation for web interface
- Implement location permission handling
- Create location accuracy indicators for users
- Add location method selection preferences

### 4. Intelligent Conversation Flow
**Goal**: Streamline user interaction with smart origin/destination detection

**Current Limitation**: Users must explicitly specify both origin and destination

**Requirements**:
- Proactive greeting asking if traveling from current location
- Smart origin detection and confirmation
- Contextual destination prompting
- Natural conversation flow for trip planning

**Implementation**:
- Enhanced Planning Agent with conversation logic
- Origin assumption and confirmation patterns
- Destination-focused follow-up prompts
- Context-aware trip planning workflows

## Technical Implementation

### Phase 1: Communication Layer
- Integrate Twilio SDK
- Add webhook endpoints
- Create message routing system
- Test SMS/WhatsApp connectivity

### Phase 2: Enhanced Location & Conversation Flow
- Implement HTML5 geolocation API for web interface
- Add mobile-responsive location detection
- Create location permission flows
- Implement intelligent greeting and origin/destination logic
- Add conversation flow patterns for trip planning

### Phase 3: Wellness Integration
- Add real-time transit monitoring
- Create delay detection system
- Implement calming message triggers
- Build CBT intervention library

### Success Metrics
- Message delivery rate >99%
- Location accuracy improvement: IP-based (±1 mile) → GPS-based (±10 meters)
- Conversation efficiency: Reduce average interaction steps for trip planning by 50%
- User satisfaction with natural conversation flow >85%
- Delay detection accuracy >90%
- User stress reduction during delays (self-reported)
- System uptime >99.9%

## Architecture Changes

### New Agents
- **Communication Agent**: Handle multi-channel messaging
- **Wellness Agent**: Provide stress relief during disruptions

### Enhanced WorldState
- Add communication preferences
- Track current transit status
- Store session-only wellness context

### Updated Tools
- **Location tool**: Enhanced with GPS/HTML5 geolocation, accuracy indicators
- **Conversation tool**: Enhanced with intelligent greeting and origin/destination flows
- **Weather tool**: Enhanced for comfort recommendations
- **Directions tool**: Include delay/disruption awareness
- **New tool**: Stress intervention delivery

## Privacy Approach
- No individual behavior profiling
- Session-only data storage
- Location data: GPS coordinates used only for current session
- Transit disruption detection without personal tracking
- GDPR/CCPA compliant by design
- User control over location precision (IP vs GPS)

## Resources Needed
- 2-3 developers (6-8 months with location enhancement)
- Twilio account and services
- Transit API subscriptions
- Mental health content consultant
- Mobile app development (for optimal GPS access)
- SSL certificates and security compliance for location handling

