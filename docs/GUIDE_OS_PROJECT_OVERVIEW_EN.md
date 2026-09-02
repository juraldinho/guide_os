# Guide OS

## The Operating System for Professional Tourism

Guide OS is a digital operating platform designed to help professional tour guides organize their work, manage their schedules, track income, receive verified business information, and build a more structured and transparent professional life.

The product began as a practical Telegram tool for working guides. Its long-term ambition is much larger: to become the trusted operational layer connecting guides, tour operators, partner businesses, knowledge, financial information, and intelligent tools across the tourism industry.

Guide OS is part of the broader **Tourism OS ecosystem** and works together with **GuideShop**, a B2B system used by tourism partner businesses to manage visits, sales, guide rewards, and payouts.

---

## 1. The Problem Guide OS Solves

Professional tourism depends on many independent participants: guides, tour operators, hotels, restaurants, museums, shops, factories, workshops, drivers, wineries, and other local partners.

These participants often work through disconnected tools and informal processes:

- schedules are kept in personal notebooks, chats, or spreadsheets;
- important information is scattered across messages;
- guides rely heavily on memory;
- commission and payment information can be unclear;
- partner relationships depend on personal contacts rather than structured data;
- professional knowledge is easily lost;
- there is no shared operational layer connecting the market.

This fragmentation creates unnecessary stress, missed opportunities, scheduling conflicts, lost information, and low transparency.

Guide OS addresses this problem by giving tourism professionals a practical system for organizing daily work today, while creating the foundation for a connected and intelligent tourism ecosystem tomorrow.

---

## 2. What Guide OS Is

Guide OS is more than a calendar, a Telegram bot, or a traditional CRM.

It is designed as a professional operating system that can bring together:

- personal work planning;
- tour and schedule management;
- income tracking;
- verified partner information;
- official sales and reward data;
- professional knowledge;
- business history;
- analytics;
- intelligent assistance;
- trusted connections between tourism participants.

The current product focuses on solving clear everyday problems for individual guides. The architecture is being developed so that Guide OS can later support tour operators, partner discovery, knowledge management, AI assistance, marketplace capabilities, financial tools, integrations, and other modules within Tourism OS.

---

## 3. Who Guide OS Is For

### Professional tour guides

Guide OS helps guides manage their calendar, avoid scheduling conflicts, organize tour information, track income, and gradually access verified information from partner businesses.

### Tour operators and coordinators

Future modules can help operators coordinate guides, preserve operational knowledge, manage partner relationships, improve quality control, and increase transparency across their workflows.

### Tourism partner businesses

Partner businesses work through GuideShop, the B2B side of the ecosystem. GuideShop connects official visits, sales, rewards, and payouts with the correct guide in Guide OS.

### The wider tourism ecosystem

Over time, Guide OS can provide shared infrastructure for hotels, restaurants, museums, shops, transport providers, workshops, factories, wineries, and other businesses that work with tourists and guides.

---

## 4. Current Guide OS Features

Guide OS currently operates primarily through Telegram, making it easy to use without requiring guides to install or learn a complex business application.

### Tour calendar

Guides can maintain a personal work calendar and see their tours by date and month.

The calendar supports:

- single-day tours;
- multi-day tours;
- days off;
- monthly views;
- daily cards;
- lists of tours for a selected period;
- quick navigation between dates and tour records.

### Tour creation and management

A guide can create and manage a tour with practical working information such as:

- tour date or date range;
- company or customer;
- city or destination;
- expected income;
- notes;
- tour status;
- payment status.

Tour information can be updated when plans change. Multi-day tours remain grouped so that the system can treat them as one connected assignment.

### Schedule conflict prevention

Before saving a tour, Guide OS can detect overlapping dates and warn the guide about a possible conflict.

This helps reduce:

- accidental double bookings;
- forgotten commitments;
- manual calendar checks;
- last-minute operational problems.

### Availability checking

Guides can check whether a particular date is free before accepting a new assignment. This provides a quick answer during conversations with tour operators or customers.

### Income tracking

Guide OS helps the guide keep a simple record of tour income and payment status.

The system can show:

- total recorded income;
- unpaid tours;
- monthly results;
- all-time statistics;
- work activity over a selected period.

This gives the guide a clearer view of personal work performance without maintaining a separate spreadsheet.

### Statistics

The product provides practical summaries for monthly and all-time activity. The goal is to help a guide understand workload, earnings, and work patterns using structured records rather than memory.

### Personal profile

Each user has a Guide OS profile and a stable internal identity. The guide can maintain a display name, while the platform assigns a permanent `guide_os_id` used for secure connections with other Tourism OS services.

### Tour reminders

Guides can enable reminders for upcoming tours and choose when they want to receive them.

Reminders reduce the risk of missing an assignment and make Guide OS useful as an active daily assistant, not only as a passive database.

### Data separation

Each guide sees only their own personal calendar and tour information. User-level access controls are a core part of the system rather than an optional feature.

### Administrative and operational tools

The current platform also includes controlled administrative capabilities such as operational reports, system notifications, broadcasts, backups, logging, and error handling.

---

## 5. Guide OS and GuideShop

Guide OS and GuideShop are two connected products with different responsibilities.

| Product | Primary user | Main responsibility |
|---|---|---|
| **Guide OS** | Tour guide | Personal schedule, work organization, professional identity, guide-facing information and future intelligent tools |
| **GuideShop** | Tourism partner business | Company operations, group visits, sales, guides, reward points, payouts, reporting and audit |

### How the connection creates value

A typical ecosystem workflow is:

1. A tourist group visits a partner business.
2. The business manager records the visit in GuideShop.
3. A sale is registered and connected to the visit.
4. GuideShop calculates the guide's reward in points.
5. The official information becomes available to the correctly linked guide through Guide OS.
6. The guide can view the company, visit, sale, points balance, and reward history.
7. In future releases, the guide can receive a notification and open the relevant record directly.

This creates value for both sides:

- businesses gain a structured CRM and clearer guide relationships;
- guides gain visibility into official visits, sales, rewards, and payouts;
- both sides work with the same verified business facts;
- the ecosystem becomes more transparent and professional.

### Clear ownership of information

The two products do not share one database and do not overwrite each other's records.

- GuideShop remains the source of truth for official companies, visits, sales, points, and payouts.
- Guide OS remains the source of truth for the guide's identity, personal calendar, and future private records.
- Communication happens through a controlled, versioned service API.
- Every request must prove the guide's identity and may return only that guide's information.

This separation makes the integration safer, easier to audit, and easier to expand.

---

## 6. Current Integration Status

The Guide OS–GuideShop integration is technically implemented through a secure, versioned foundation and isolated staging environments. It is being validated in controlled stages before full production activation.

The implemented foundation includes:

- a permanent Guide OS identity for every guide;
- a verified account-linking lifecycle;
- one-time linking requests;
- explicit guide confirmation;
- signed service-to-service authentication;
- protection against repeated or replayed requests;
- user-bound navigation and deep links;
- a read-only GuideShop API for companies, visits, sales, points, and history;
- strict separation between guides and companies;
- reconciliation data for detecting inconsistencies;
- feature flags that keep integration functions disabled until an environment is ready;
- isolated API staging that does not use production databases or credentials.

The integration is intentionally being released in stages. Production activation, automatic events, and user notifications will only be enabled after end-to-end security, isolation, recovery, and operational checks are complete.

This approach protects users and business data while allowing the platform to grow on a reliable foundation.

---

## 7. Key Benefits

### Benefits for guides

- **Less administrative chaos** — tours, dates, notes, income, and payment status are kept in one place.
- **Fewer scheduling mistakes** — conflict detection helps prevent double booking.
- **Faster decisions** — availability can be checked during a conversation with a client or operator.
- **Better financial visibility** — guides can understand recorded income, unpaid work, official GuideShop sales, and reward history.
- **Reduced dependence on memory** — professional information becomes a structured asset.
- **Simple access** — Telegram provides a familiar interface with a low learning barrier.
- **Verified business information** — official GuideShop data comes from the partner business responsible for the transaction.
- **A portable professional identity** — the permanent Guide OS identity can support future services and trusted relationships.

### Benefits for partner businesses

- **Structured visit management** — every group visit can be recorded and tracked.
- **Transparent sales and rewards** — sales, categories, reward calculations, and payouts have a clear history.
- **Better guide relationships** — the correct guide can receive verified information without informal manual reporting.
- **Operational accountability** — roles, audit records, reports, and company-level access controls improve control.
- **A channel back to the guide** — GuideShop becomes part of a wider ecosystem rather than an isolated CRM.

### Benefits for the tourism market

- **More transparency** between guides, operators, and partner businesses;
- **higher professional standards** through structured processes;
- **better preservation of knowledge** that would otherwise remain in private chats or memory;
- **more reliable decisions** based on history and verified data;
- **stronger network effects** as more participants use compatible systems;
- **a foundation for responsible AI**, analytics, and automation based on clean operational data.

---

## 8. Product Principles

Guide OS is built around several long-term principles.

### Transparency

Important statuses, conditions, rewards, and histories should be understandable to the people responsible for them.

### Reliability

The platform must be dependable enough for real professional work. It should reduce uncertainty rather than introduce new uncertainty.

### Practicality

Every feature should solve a real operational problem. The product is not built around technology for its own sake.

### Human-first intelligence

AI should support professional judgment, not replace human experience, cultural understanding, responsibility, or relationships.

### Quality data before automation

Useful automation requires structured processes and trustworthy data. Guide OS first creates order, then builds intelligence on top of it.

### Trust before growth

Security, clear ownership, understandable rules, and careful handling of data are more important than uncontrolled expansion.

### Ecosystem thinking

Guide OS is useful to an individual guide today, but its greatest value appears when guides, businesses, and operators can cooperate through a trusted common infrastructure.

---

## 9. Future Development

Guide OS is designed as a modular platform. Future features may be introduced gradually after validation and product approval.

### Deeper GuideShop integration

Planned development includes:

- production activation of secure account linking;
- automatic notifications about new visits, sales, and points changes;
- direct deep links from notifications to the relevant record;
- recovery after missed events;
- stronger reconciliation and operational monitoring;
- a controlled pilot followed by gradual rollout.

### Professional partner network

Guide OS can evolve into a structured network of trusted tourism partners, helping professionals understand:

- who they have worked with;
- which conditions were agreed;
- which partners are reliable;
- what happened during previous cooperation;
- where better opportunities may exist.

### Knowledge management

Future modules can help guides and operators preserve:

- destination knowledge;
- partner information;
- route notes;
- operational instructions;
- cultural and historical materials;
- lessons learned from previous tours;
- reusable professional workflows.

### AI assistance

AI is expected to become an assistant for structured professional work. Possible future capabilities include:

- organizing notes and knowledge;
- preparing tour information;
- summarizing operational history;
- identifying scheduling or financial patterns;
- suggesting next actions;
- helping compare partners or options;
- supporting planning and decision-making;
- reducing repetitive administrative work.

AI features will be introduced only where they provide clear value and can operate on trustworthy data.

### Personal places and external sales

A future Guide OS module may allow a guide to maintain private personal places and record external sales or income that did not originate in GuideShop.

These records would:

- belong only to the guide;
- remain separate from official GuideShop companies;
- not create a public catalogue automatically;
- require explicit rules before they can affect official points.

Any future points claim for an external sale would require separate fraud prevention, legal, tax, and redemption policies.

### Tour operator tools

Future versions may support operator workflows such as:

- guide coordination;
- team scheduling;
- partner management;
- quality control;
- shared operational knowledge;
- task and status management;
- analytics across tours and teams.

### Marketplace and discovery

A marketplace or discovery layer may eventually help participants find suitable partners and services. It would not be a simple public directory: the long-term goal is to combine discovery with context, reliability, history, professional standards, and transparent rules.

### Analytics and financial tools

As the ecosystem grows, Guide OS can provide more advanced analytics around workload, income, partner performance, rewards, operational efficiency, and market trends.

### APIs and ecosystem modules

The architecture can support additional Tourism OS products and approved third-party integrations without forcing every function into one application.

---

## 10. Long-Term Vision

The long-term vision is to make Guide OS the trusted operating system of professional tourism.

In this vision:

- guides manage their work and professional knowledge in one place;
- tour operators coordinate people and processes more effectively;
- partner businesses use GuideShop to manage official commercial activity;
- verified information moves safely between systems;
- participants understand their responsibilities and history;
- AI helps people make better decisions without replacing professional judgment;
- the market becomes more organized, transparent, and reliable.

Guide OS is not intended to replace human relationships in tourism. Its role is to support those relationships with better structure, memory, data, and trust.

---

## 11. Why Guide OS Can Become a Platform

Guide OS has several characteristics that give it platform potential:

1. **It begins with a frequent daily use case.** Calendar, tours, reminders, and income give guides an immediate reason to return.
2. **It creates a stable professional identity.** This enables secure relationships across products.
3. **It connects supply-side businesses through GuideShop.** Official visits and commercial data can reach the relevant guide.
4. **It preserves structured history.** Over time, this becomes valuable operational knowledge.
5. **It is modular.** New services can be added without turning the product into one monolithic application.
6. **It is designed around trust.** Data ownership, isolation, explicit linking, and staged activation are part of the foundation.
7. **It can support network effects.** Every additional guide, operator, and partner can make the ecosystem more useful to others.

---

## 12. Current Position in One Sentence

**Guide OS is a working Telegram-based professional organizer for tour guides that is evolving into a secure, connected operating platform where guides can manage their own work and access verified business information from GuideShop.**

---

## 13. Short Summary

Guide OS helps tour guides organize tours, dates, income, reminders, and professional information. It reduces scheduling mistakes, replaces scattered notes and spreadsheets, and gives guides a clearer view of their work.

Together with GuideShop, it creates a bridge between guides and tourism partner businesses. GuideShop manages official visits, sales, reward points, and payouts; Guide OS gives the correctly linked guide secure access to that information.

The current product and integration foundation are already implemented and are being validated through controlled staging. Future development can expand Guide OS into knowledge management, AI assistance, partner discovery, operator tools, analytics, marketplace capabilities, external-sale workflows, and a wider Tourism OS ecosystem.

The central idea is simple: **professional tourism should operate through better structure, trusted information, transparency, and intelligent tools—not through fragmented chats, memory, and disconnected spreadsheets.**

## Approved future daily tips roadmap

A bot-first daily tips feature is approved but not implemented: one amount per user and calendar date, independent of tours, followed by shared API and Mini App parity. See [`TIPS_ROADMAP.md`](TIPS_ROADMAP.md).

## Active GuideShop Mini App roadmap

The owner activated GSMA0 for a scalable third Mini App module combining user-owned personal companies/commissions with the official read-only GuideShop catalog. See [`mini_app/GUIDESHOP_MINIAPP_ROADMAP.md`](mini_app/GUIDESHOP_MINIAPP_ROADMAP.md).
