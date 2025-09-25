# Vaya Transport Assistant - Product Requirements Document (PRD)

## Executive Summary

**Project Name:** Vaya Enhanced Transport Assistant
**Version:** 2.0
**Date:** September 25, 2025
**Team:** KuralabPublicTransport

Vaya is evolving from a lightweight AI-powered urban navigation companion to a comprehensive stress-reducing public transport assistant. This PRD outlines the existing architecture and future enhancements including Twilio integration and AI-powered stress reduction chatbot functionality.

## 1. Current Architecture Overview

### 1.1 Existing System Architecture

**Core Technology Stack:**
- **Backend:** Python 3.8+
- **LLM Framework:** LangChain with Google Gemini
- **Architecture Pattern:** Two-Agent A2A (Agent-to-Agent)
- **APIs:** Google Maps, Google Geocoding, Weather APIs
- **Deployment:** Local CLI, Docker containerization, Render cloud deployment

### 1.2 Current Agent Architecture

**Planning Agent:**
- Receives user queries and generates structured execution plans (JSON)
- Uses Gemini LLM (low temperature) for deterministic planning
- Handles slot filling, pronoun resolution, and ambiguous queries
- Returns plans as deltaState patches to shared WorldState

**Execution Agent:**
- Executes plan steps using LLM reasoning and tool selection
- Manages slot references, tool output merging, and error handling
- Generates final user-facing responses via LLM
- Handles placeholder substitution and context-aware follow-ups

**Coordinator:**
- Orchestrates Planner → Executor flow
- Loads/saves conversation memory to disk
- Handles WorldState initialization and error fallback

### 1.3 Current Tool Ecosystem

- **Location Tools:** Geolocate, Geocode, ReverseGeocode
- **Information Tools:** Weather, Places Search, Place Details
- **Navigation Tools:** Directions (public transit support)
- **Communication Tools:** Basic conversation handling

### 1.4 Current State Management

**WorldState (Blackboard Architecture):**
- Central structured state shared by all agents
- Tracks slots (origin/destination), context, plans, and memory
- Uses deltaState patches with deepMerge() for state updates
- Persistent conversation memory in JSON format

## 2. Identified Gaps and Pain Points

### 2.1 Current Limitations

**User Experience:**
- Limited to CLI and web interfaces
- No proactive communication capabilities
- Lacks emotional intelligence for stressed commuters
- Missing real-time transit disruption alerts

**Integration Capabilities:**
- No SMS/messaging integration
- Limited notification system
- No multi-channel communication support

**Stress Management:**
- No anxiety/stress detection or reduction features
- Missing personalized comfort suggestions
- Lack of emotional support during transit disruptions

### 2.2 Market Opportunity

Based on research, key public transport stress factors include:
- **Environmental:** Crowding, poor conditions, hostile attitudes
- **Time-related:** Delays, unpredictable wait times, transfer complexity
- **Physical/Psychological:** Anxiety, exhaustion, safety concerns
- **Service Quality:** Unreliable service, lack of information

## 3. Future Architecture Vision

### 3.1 Enhanced System Architecture

**Multi-Channel Communication Layer:**
- Twilio SMS/WhatsApp integration
- Proactive notification system
- Multi-modal interaction support (voice, text, rich media)

**AI Stress Reduction Engine:**
- Emotion detection and analysis
- Personalized coping strategy recommendations
- Mindfulness and breathing exercise delivery
- Predictive stress intervention

**Advanced Agent Architecture:**
- **Planning Agent** (existing, enhanced)
- **Execution Agent** (existing, enhanced)
- **Communication Agent** (new)
- **Wellness Agent** (new)
- **Alert Agent** (new)

### 3.2 Technology Stack Evolution

**Current → Future:**
- Python + LangChain → Enhanced with Twilio SDK
- Google APIs → Enhanced with transit data feeds
- Local CLI → Multi-channel (SMS, WhatsApp, Web, Voice)
- Basic memory → Advanced user profiling and preference learning

## 4. New Feature Requirements

### 4.1 Twilio Integration Requirements

#### 4.1.1 SMS Capabilities
**Core Features:**
- Bidirectional SMS communication
- Rich formatting support
- Media attachment handling (MMS)
- Delivery status tracking

**Architecture Requirements:**
- Enterprise-grade account structure with subaccounts
- HTTP Basic authentication with API keys
- Error handling with automatic fallback mechanisms
- Rate limiting and message prioritization queues

**Implementation Specifications:**
```
Twilio Integration Layer:
├── Authentication Manager
├── Message Router (SMS/WhatsApp)
├── Delivery Status Handler
├── Error Recovery System
└── Rate Limiting Controller
```

#### 4.1.2 WhatsApp Business API
**Core Features:**
- Two-way WhatsApp conversations
- Rich media support (images, documents, location)
- Template message support for notifications
- Interactive buttons and quick replies

**Business Use Cases:**
- Booking confirmations and updates
- Real-time trip notifications
- Customer support conversations
- Identity verification

#### 4.1.3 Multi-Channel Architecture
**Features:**
- Unified conversation management across channels
- Context preservation between SMS and WhatsApp
- Channel-appropriate message formatting
- Fallback mechanisms (WhatsApp → SMS)

### 4.2 Stress-Reduction Chatbot Requirements

#### 4.2.1 Transit Disruption Detection System
**Core Capabilities:**
- Real-time transit delay and disruption monitoring
- Service interruption impact assessment
- Contextual trigger identification (delays, service changes, crowding alerts)
- Anonymous stress response pattern recognition (no individual profiling)

**Technical Requirements:**
- Real-time transit API integration
- Service disruption severity classification
- Automated calming intervention triggers
- Privacy-first approach with no personal behavior tracking

#### 4.2.2 Intervention Strategies
**Evidence-Based Techniques:**
- Cognitive Behavioral Therapy (CBT) techniques
- Mindfulness exercises and breathing techniques
- Cognitive restructuring guidance
- Progressive muscle relaxation scripts

**Universal Support Features:**
- Situation-specific calming techniques (delays, crowding, disruptions)
- General stress management resources
- Non-personalized intervention recommendations
- Cultural and linguistic adaptation without individual profiling

#### 4.2.3 Proactive Support System
**Features:**
- Real-time delay and disruption-triggered calming guidance
- Immediate comfort messages when service interruptions are detected
- Contextual stress relief during active transit disruptions
- General wellness check-ins during extended wait times (no personal tracking)

**Safety Considerations:**
- Clear boundaries about therapeutic limitations
- Crisis escalation protocols
- Professional mental health resource referrals
- Compliance with mental health AI guidelines

### 4.3 Enhanced Agent Architecture

#### 4.3.1 Communication Agent (New)
**Responsibilities:**
- Channel-specific message formatting
- Delivery orchestration across SMS/WhatsApp
- Conversation context management
- User preference learning

**Integration Points:**
- Twilio SDK for message delivery
- WorldState for conversation memory
- User profile for channel preferences
- Analytics for message effectiveness

#### 4.3.2 Wellness Agent (New)
**Responsibilities:**
- Context-aware stress intervention delivery
- Universal calming strategy selection based on transit conditions
- General wellness content delivery (no personalization)
- Crisis detection and escalation

**Core Algorithms:**
- Transit disruption severity analysis
- CBT technique library
- Universal intervention engine
- Safety monitoring system

#### 4.3.3 Alert Agent (New)
**Responsibilities:**
- Real-time transit data monitoring
- Disruption impact assessment
- Proactive calming notification triggering
- Context-aware alert delivery (no personal profiling)

**Data Sources:**
- Transit authority feeds
- Third-party transit APIs
- Current user location (session-only)
- General disruption pattern analysis

## 5. Technical Implementation Plan

### 5.1 Phase 1: Twilio Integration Foundation (Months 1-2)

**Core Infrastructure:**
- Twilio account setup with enterprise architecture
- SMS bidirectional communication
- Basic webhook handling for incoming messages
- Integration with existing WorldState system

**Deliverables:**
- Twilio SDK integration
- Message routing infrastructure
- Basic SMS conversation support
- Error handling and logging

### 5.2 Phase 2: WhatsApp and Multi-Channel (Months 3-4)

**Enhanced Communication:**
- WhatsApp Business API integration
- Rich media support implementation
- Cross-channel conversation management
- Template message system

**Deliverables:**
- WhatsApp chatbot functionality
- Media handling capabilities
- Channel fallback mechanisms
- Unified conversation history

### 5.3 Phase 3: Stress Reduction Engine (Months 5-6)

**AI Wellness Features:**
- Transit disruption detection system
- CBT technique library
- Universal intervention engine
- Safety monitoring implementation

**Deliverables:**
- Delay-triggered calming algorithms
- Context-aware intervention delivery system
- General wellness resource library
- Crisis detection protocols

### 5.4 Phase 4: Proactive Intelligence (Months 7-8)

**Advanced Features:**
- Transit disruption prediction modeling
- Proactive calming alert system
- Context-aware guidance optimization
- Analytics and system optimization

**Deliverables:**
- Transit disruption prediction algorithms
- Real-time calming alert system
- Context-aware intervention optimization
- Performance analytics dashboard

## 6. Data Architecture and Privacy

### 6.1 Enhanced Data Model

**User Profile Extensions:**
- Communication preferences (SMS vs WhatsApp)
- General wellness resource preferences
- Crisis contact information (optional)
- Language and accessibility preferences

**New Data Entities:**
- Message History (cross-channel, session-based)
- Transit Disruption Events
- General Intervention Outcomes (anonymized)
- Alert Delivery Preferences

### 6.2 Privacy and Security

**Data Protection:**
- End-to-end encryption for all communications
- GDPR/CCPA compliance for EU/California users
- Privacy-by-design with no behavioral tracking
- Session-only data storage with explicit consent

**Twilio Security:**
- API key management and rotation
- Webhook signature validation
- Rate limiting and abuse prevention
- Audit logging for all communications

## 7. Success Metrics and KPIs

### 7.1 Technical Metrics
- Message delivery success rate (>99.5%)
- Response time for stress interventions (<30 seconds)
- System uptime and reliability (99.9%)
- Cross-channel conversation continuity

### 7.2 User Experience Metrics
- User-reported stress reduction during delays (target: 25% improvement)
- Engagement rates with calming guidance content
- User retention and active usage during disruptions
- Satisfaction scores for proactive calming support

### 7.3 Business Metrics
- Cost per message/conversation
- User acquisition through new channels
- Support ticket reduction
- Revenue impact from enhanced user experience

## 8. Risk Assessment and Mitigation

### 8.1 Technical Risks
- **Twilio API limits:** Implement queuing and rate limiting
- **LLM response quality:** Add fallback mechanisms and human review
- **System integration complexity:** Phased rollout with feature flags

### 8.2 Regulatory and Safety Risks
- **Mental health AI regulations:** Strict compliance with emerging guidelines
- **Data privacy concerns:** Privacy-by-design approach
- **Crisis management:** Clear escalation procedures and professional referrals

### 8.3 Business Risks
- **User adoption:** Comprehensive onboarding and education
- **Cost scaling:** Usage-based pricing models and optimization
- **Competition:** Continuous innovation and user feedback incorporation

## 9. Future Roadmap

### 9.1 Advanced AI Features (Year 2)
- Enhanced transit disruption prediction algorithms
- Context-aware guidance optimization
- Integration with smart city transport systems
- Advanced real-time service monitoring

### 9.2 Platform Expansion (Year 2-3)
- Voice integration (Twilio Voice API)
- Video calling support for crisis intervention
- IoT integration for smart city transport data
- Third-party mental health platform partnerships

### 9.3 Global Scaling (Year 3+)
- Multi-language support for diverse markets
- Cultural adaptation of universal calming techniques
- Partnership with transit authorities worldwide
- White-label solutions for transport operators

## 10. Resource Requirements

### 10.1 Development Team
- 2-3 Backend developers (Python/LangChain expertise)
- 1 Twilio/Communications specialist
- 1 AI/ML engineer for wellness features
- 1 Mental health consultant (ongoing advisor)
- 1 DevOps engineer for scalable infrastructure

### 10.2 Infrastructure and Tools
- Twilio account with appropriate service plans
- Enhanced cloud infrastructure for multi-channel support
- Mental health AI compliance tools
- Advanced analytics and monitoring platforms

### 10.3 Budget Estimates
- Development: $250K-350K for full implementation
- Twilio services: $5K-15K monthly (usage-based)
- Infrastructure scaling: $3K-8K monthly
- Compliance and consulting: $25K-50K one-time

## 11. Conclusion

This PRD outlines the evolution of Vaya from a basic transport assistant to a comprehensive, stress-reducing public transport companion. The integration of Twilio's communication platform with AI-powered wellness features addresses critical gaps in current public transport user experience.

The phased implementation approach ensures manageable risk while delivering incremental value to users. The focus on evidence-based stress reduction techniques, combined with proactive communication capabilities, positions Vaya as a leader in empathetic AI for urban mobility.

Success will be measured not just through technical metrics, but through genuine improvements in user well-being during their daily commutes, making public transport a less stressful and more supportive experience for millions of urban travelers.

---

**Next Steps:**
1. Stakeholder review and approval
2. Technical architecture deep-dive sessions
3. Twilio partnership and account setup
4. Mental health advisory board formation
5. Development sprint planning and resource allocation

*Document Version: 1.0*
*Last Updated: September 25, 2025*
*Author: AI Assistant with KuralabPublicTransport Team*