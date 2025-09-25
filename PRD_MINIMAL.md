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

## Technical Implementation

### Phase 1: Communication Layer
- Integrate Twilio SDK
- Add webhook endpoints
- Create message routing system
- Test SMS/WhatsApp connectivity

### Phase 2: Wellness Integration
- Add real-time transit monitoring
- Create delay detection system
- Implement calming message triggers
- Build CBT intervention library

### Success Metrics
- Message delivery rate >99%
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
- Weather tool: Enhanced for comfort recommendations
- Directions tool: Include delay/disruption awareness
- New tool: Stress intervention delivery

## Privacy Approach
- No individual behavior profiling
- Session-only data storage
- Transit disruption detection without personal tracking
- GDPR/CCPA compliant by design

## Resources Needed
- 2-3 developers (4-6 months)
- Twilio account and services
- Transit API subscriptions
- Mental health content consultant

---
*Minimal PRD based on actual codebase analysis*