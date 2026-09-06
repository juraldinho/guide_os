# Guide OS

## The Operating System for Professional Tourism

> Project overview updated on September 5, 2026.

Guide OS is a digital operating platform for professional tour guides. It helps guides manage schedules, tours, availability, income, personal working information, partner relationships, and verified business activity in one place.

The product now combines a production Telegram bot, a Telegram Mini App, secure production integration with GuideShop, guide-owned personal places, and the guide-facing foundation for Guide Operator assignments.

Guide OS is the guide-centered product within the wider **Tourism OS ecosystem**:

- **Guide OS** is the personal professional workspace for the guide;
- **GuideShop** is the operating and commercial system for tourism partner businesses;
- **Guide Operator** is the structured tour-assignment system for tour operators.

Together, these products are designed to replace fragmented chats, spreadsheets, screenshots, informal agreements, and memory-dependent workflows with connected and trusted professional infrastructure.

---

## 1. Why Guide OS Exists

Professional tourism depends on guides, tour operators, hotels, restaurants, museums, shops, factories, workshops, drivers, and other local partners. They rely on one another, but their work is often managed through disconnected tools.

Common problems include:

- schedules stored in notebooks, chats, and spreadsheets;
- tour instructions scattered across messages and documents;
- difficult-to-track changes;
- dependence on personal memory;
- unclear partner, commission, and payment information;
- professional knowledge that is easily lost;
- different organizations maintaining incompatible versions of the same facts.

This fragmentation creates stress, double bookings, missed information, inefficient coordination, payment uncertainty, and service-quality problems.

Guide OS begins with the guide's daily needs and connects the wider ecosystem around verified identity, clear data ownership, structured workflows, and responsible technology.

---

## 2. What Guide OS Is

Guide OS is more than a calendar, Telegram bot, or traditional CRM. It is designed to bring together:

- personal work planning;
- tour and availability management;
- structured operator assignments;
- guide-owned places and records;
- income and payment tracking;
- official partner and visit information;
- verified reward points and payout history;
- operational notifications;
- professional history, analytics, and future intelligent assistance.

The platform solves practical problems today while establishing the trust and technical foundations required for a larger tourism ecosystem.

---

## 3. Who the Platform Serves

### Tour guides

Guides use Guide OS as their personal professional workspace. They organize tours, protect availability, track work and income, maintain private records, view official GuideShop activity, and receive structured Guide Operator assignments.

### Tourism partner businesses

Shops, factories, workshops, restaurants, museums, and other venues use GuideShop to manage visits, sales, points, payouts, staff permissions, reports, and guide relationships.

### Tour operators

Tour operators will use Guide Operator to create structured tours, select consent-connected guides, send offers, publish updates, and deliver complete working packages into Guide OS.

---

## 4. Guide OS Features Available Today

### Professional calendar

Guide OS supports:

- single-day and multi-day tours;
- days off;
- daily and monthly Telegram views;
- day, week, and month Mini App views;
- optional start and end times;
- reserved and confirmed statuses;
- paid and unpaid statuses;
- compatibility with older full-day records;
- fast access to each assignment.

The central experience answers a frequent working question: **“Am I free on this date?”**

### Tour creation and editing

A guide can maintain the date or date range, time, company or customer, city, expected income, notes, booking status, and payment status. Multi-day records remain grouped as one assignment.

### Conflict prevention

Guide OS detects overlapping commitments before they are saved. Timed tours may share a day when they do not overlap; full-day entries reserve the entire date. Guides can also prepare clear availability information for a client or operator.

### Income and summaries

The platform shows recorded income, unpaid work, monthly results, all-time summaries, and tour activity. This replaces a separate spreadsheet for many everyday use cases.

### Professional identity

Every user has a stable, immutable `guide_os_id`. It connects the correct person across Tourism OS services without relying only on names, phone numbers, or Telegram IDs.

### Reminders and notifications

Guides receive tour reminders. Guide OS also consumes verified GuideShop events and delivers Telegram notifications with safe links to current information. Processing is durable and idempotent, so repeated events do not create duplicate notifications.

### Personal places

Guide OS supports private, guide-owned places. A guide can create, view, edit, and deactivate a place while retaining inactive records safely. Personal places are not automatically treated as official GuideShop companies.

### Telegram Mini App

The responsive Mini App uses the same production services and data as the bot. Its public production pilot is active and owner-validated. It offers a visual experience for calendar navigation, tours, availability, reports, settings, personal records, and integrated modules.

The bot and Mini App are equal interfaces over shared business rules. The frontend has no direct database access and does not maintain a second calendar system. A separate formal general-release declaration has not yet been made.

---

## 5. Guide OS and GuideShop

GuideShop is the B2B partner-business side of Tourism OS.

### What GuideShop manages

- partner companies;
- owners, managers, and delegated permissions;
- guide directories and verified links;
- tourist-group visits;
- sale categories and multiple sales per visit;
- payment methods;
- reward-point calculation;
- payout history;
- reports, exports, audit, and backups.

Sales are recorded in USD; guide rewards use PTS in the current reward model.

### How the production integration works

The Guide OS–GuideShop integration is active in production:

1. A business records a visit in GuideShop.
2. The visit is connected to a guide who may be securely linked to Guide OS.
3. GuideShop records sales and calculates points.
4. GuideShop publishes a durable domain event.
5. Guide OS receives and deduplicates the event.
6. Guide OS refreshes authoritative information through the read-only API.
7. Guide OS sends the relevant Telegram notification.
8. The guide opens a safe deep link to the official information.

GuideShop publishes business events but does not send guide-facing Telegram notifications. Guide OS owns notification delivery.

### Information available to the guide

The current guide-facing experience can show:

- connected companies and public contact details;
- official visits and visit details;
- points associated with a visit;
- pending and credited totals;
- company-level points breakdown;
- points and payout history.

Internal identifiers are not exposed. Guide-facing navigation focuses on useful company, visit, and points information, while official sales remain owned by GuideShop.

### Clear ownership and trust

- GuideShop is authoritative for official companies, visits, sales, points, and payouts.
- Guide OS is authoritative for guide identity, personal calendar, personal places, guide-facing state, and private records.
- The products never access each other's SQLite databases directly.
- Current state comes from protected reads; events act as signals rather than replacing authoritative data.
- Every request is identity-bound and company/guide scoped.
- Linking is optional, explicit, audited, conflict-safe, and lifecycle-controlled.
- Unlinked guides continue to work normally in GuideShop.

### Production reliability

The integration completed its staged rollout and operational closure. Linking, reads, event consumption, and notifications are active. Deduplication, checkpoints, watermarks, reconciliation, recovery, canary notifications, deep links, and monitored operation have been validated. Routine monitoring continues as normal operational work.

---

## 6. Guide OS and Guide Operator

Guide Operator is the operator-to-guide assignment layer of Tourism OS. It replaces fragmented assignments sent through messages, screenshots, and documents with one structured, versioned working package.

### Intended operator workflow

An operator will be able to:

1. create a tour manually;
2. build a day-by-day program with ordered events;
3. add group information and drivers by day;
4. specify meals, tickets, transport, allowance, and instructions;
5. publish contacts;
6. select a consent-connected guide;
7. send an offer;
8. publish controlled updates or cancellation.

### Guide OS-side capabilities already implemented

- Guide Operator connection and consent UX;
- assignment-offer intake;
- accept and decline semantics;
- lifecycle lists and details;
- accepted assignment calendar projection;
- cancelled assignment views;
- ordinary version updates and unread acknowledgement;
- critical change confirmation or rejection;
- report semantics;
- authenticated inbound event routes;
- authenticated guide discovery and availability reads.

### Working package

The structured package is designed to contain the tour overview, responsible operator, today's program, complete itinerary, group context, drivers, working conditions, contacts, version history, and a private note owned by Guide OS.

### Current Guide Operator status

Guide Operator is not yet a deployed production service.

Completed in its repository:

- architecture, domain model, and state machines;
- responsive React/TypeScript/Vite mock prototype;
- tested FastAPI, SQLAlchemy, and Alembic backend baseline;
- tour persistence and operator API;
- secure guide-connection foundation;
- proposal, acceptance, and decline model;
- cancellation command;
- immutable versions and change classification;
- critical-version publication lock;
- idempotency and transactional outbox persistence;
- service authentication;
- canonical event envelopes aligned with Guide OS intake.

Still pending:

- running PostgreSQL infrastructure;
- operator authentication;
- production frontend connected to the API;
- Guide Operator Telegram notifications;
- staging deployment and production pilot.

Local GO9A HTTP E2E against sibling Guide OS is complete. Feature flags remain off outside that harness. Reconciliation, notifications, frontend wiring, and deployment still require explicit approval.

### Ownership boundaries

- Guide Operator owns master tours, assignments, published versions, and operator audit.
- Guide OS owns guide identity, consent, calendar projection, guide-facing state, acknowledgements, and private notes.
- Synchronization uses protected APIs and versioned events, not shared database access.

---

## 7. The Three-Product Ecosystem

| Product | Primary user | Source-of-truth responsibility | Current position |
|---|---|---|---|
| **Guide OS** | Guide | Identity, personal calendar, personal places, guide state and notifications | Production bot; public Mini App pilot; GuideShop integration active |
| **GuideShop** | Partner business | Companies, official visits, sales, PTS, payouts and partner audit | Production CRM and production Guide OS integration |
| **Guide Operator** | Tour operator | Master tours, assignments, versions and operator audit | Backend/prototype implemented; local HTTP E2E proven; deployment pending |

GuideShop tells the guide what officially happened at a partner business. Guide Operator tells the guide what work was assigned and what changed. Guide OS brings these responsibilities together with the guide's personal schedule, records, and tools.

---

## 8. Key Benefits

### For guides

- one workspace for personal tours, operator assignments, partner activity, and private records;
- fewer scheduling mistakes;
- less dependence on memory;
- clearer personal income and official points information;
- reliable, versioned assignment instructions;
- familiar access through Telegram and a Mini App;
- a portable verified professional identity;
- privacy through explicit consent and owner-scoped personal data.

### For partner businesses

- structured visit and sales operations;
- transparent points and payout history;
- controlled staff permissions;
- auditable guide relationships;
- a verified channel into the guide's professional workspace.

### For tour operators

- one structured source for tour instructions;
- explicit offer and decision states;
- guide availability and identity;
- versioned updates instead of contradictory messages;
- controlled cancellations and critical changes;
- better accountability and operational history.

### For the tourism industry

- greater transparency and clearer ownership;
- stronger professional standards;
- preserved operational knowledge;
- less fragmentation;
- reliable data for analytics and future AI;
- network effects across guides, operators, and businesses.

---

## 9. Security and Trust by Design

Trust is a product feature. The ecosystem uses:

- immutable guide identities;
- explicit linking consent and verified evidence;
- server-side user, guide, and company boundaries;
- signed short-lived service credentials;
- replay protection;
- protected internal identifiers and secrets;
- fail-closed feature configuration;
- durable, deduplicated, reconcilable events;
- isolated staging and production environments;
- clear data authority for every product.

Names and phone numbers alone are not treated as sufficient proof for automatic identity matching.

---

## 10. Product Principles

- **Practical value first:** every feature must solve a real working problem.
- **Infrastructure before feature accumulation:** new modules must strengthen the system rather than create new fragmentation.
- **Trust before uncontrolled growth:** security, consent, reliability, and auditability come first.
- **Quality data before automation:** useful intelligence requires structured and trustworthy information.
- **Human-first AI:** technology supports professional judgment instead of replacing it.
- **Modular ecosystem design:** each product keeps a clear responsibility and integrates through controlled contracts.

---

## 11. Future Development

Future work is separated into approval-based product streams. Planned direction should not be confused with released functionality.

### Completing Guide Operator

Potential next stages include reconciliation, Telegram assignment notifications, operator authentication, a live frontend, isolated staging E2E, and a controlled pilot.

### Daily tips

A planned Guide OS feature may allow one tip amount per guide and calendar date, independent of tours. Implementation has not started.

### Google Calendar import

A future read-only import may show external events and allow a guide to manually convert one into a native Guide OS tour. Implementation has not started.

### External outcomes and points

Personal places provide a foundation for future self-reported external outcomes. These must remain separate from official GuideShop data. Any official PTS claim will require explicit verification, anti-fraud, legal, tax, and redemption rules.

### AI and knowledge

Future AI may help structure tour information, summarize history, prepare briefs, find missing details, identify schedule patterns, organize professional knowledge, and reduce repetitive administration. AI will be added only where data quality and responsibility make it genuinely useful.

### Analytics and trusted discovery

Later modules may provide deeper workload, partner, assignment, and performance analytics. A future marketplace may combine discovery with verified identity, context, history, and professional standards rather than acting as a simple public directory.

---

## 12. Current Status at a Glance

### Live or active

- Guide OS Telegram bot;
- Guide OS–GuideShop production linking and reads;
- GuideShop event feed and Guide OS notifications;
- personal calendar, income, reminders, profile, and personal places;
- Guide OS Mini App public production pilot;
- GuideShop production CRM;
- monitored and reconcilable event processing.

### Implemented but not fully deployed end to end

- Guide Operator backend and responsive prototype;
- Guide OS Guide Operator module and inbound integration;
- assignment versions, cancellations, critical confirmations, consent, discovery, and availability foundations.

### Planned or not yet activated

- Guide Operator reconciliation, notifications, and production deployment;
- Guide Operator Telegram notifications;
- Google Calendar import;
- daily tips;
- official external-sale PTS claims;
- broader AI, knowledge, analytics, and marketplace modules.

---

## 13. Long-Term Vision

Guide OS aims to become the trusted operating system of professional tourism: a place where guides manage work, knowledge, identity, and opportunities; operators coordinate structured assignments; partner businesses manage official commercial activity; and verified information moves safely between products.

The goal is not to replace human relationships or professional judgment. It is to support them with better structure, memory, clarity, accountability, and intelligent tools.

---

## 14. One-Sentence Description

**Guide OS is a production digital workspace for tour guides that combines personal scheduling, income, records, and verified GuideShop activity while building the structured assignment connection to tour operators through Guide Operator.**

---

## 15. Short Shareable Summary

Guide OS helps professional tour guides manage calendars, tours, availability, income, reminders, personal places, and integrated business information through Telegram and a responsive Mini App.

It works in production with GuideShop, the partner-business CRM of Tourism OS. GuideShop manages official visits, sales, points, and payouts, while Guide OS securely presents the relevant information to the linked guide and delivers notifications.

The ecosystem is also developing Guide Operator, a structured assignment platform for tour operators. Its backend, prototype, assignment lifecycle, versioning, Guide OS-side module, and local HTTP E2E are substantially implemented, while reconciliation, notifications, and production deployment remain future controlled stages.

The broader vision is to replace fragmented chats and spreadsheets with structured workflows, clear ownership, professional identity, transparent information, and responsible intelligent tools.
