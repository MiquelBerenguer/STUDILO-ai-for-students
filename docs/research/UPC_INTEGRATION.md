# UPC integration: can Novi pull a student's courses, schedule and materials automatically?

Research date: 2026-09-26. Scope: investigation only; no integration code was added to the product.

**How claims are marked**
- **[Verified]** means I read it in official documentation or a primary source (UPC, FIB or Moodle
  pages, Moodle source code), or observed it in a response.
- **[Unverified]** means it is an inference, a forum post or an assumption, or it needs a check that
  requires a login.

**What I touched**
- Public web pages only, plus **one unauthenticated request** to Atenea's public mobile-config
  endpoint (`tool_mobile_get_public_config`). This is the same call the official Moodle app makes
  before it shows the login screen. It returns site settings, no personal data.
- No login endpoint was called and no credentials were used. Nothing below required your account.
  Checks that would need it are listed under "Unknowns" for your approval.

---

## 0. Recommendation in one paragraph

**Go, but only for the sanctioned, student-initiated paths. No-go for any automatic login into Atenea
without a formal agreement with UPC.**

The smallest useful integration is **"paste your Atenea calendar link"**. It is a one-step,
password-free import of deadlines and course events, which reuses the `.ics` import Novi already has.
Add to it:
- automatic syllabus retrieval from the **public course guides** (guies docents);
- school-specific timetable feeds: **SIA's `.ics` export** for EETAC and the **FIB API** for FIB.

Full "log in with UPC and everything is imported" is technically possible: Atenea has mobile web
services enabled and uses a browser SSO flow. However, a third-party app would be impersonating the
official Moodle app to obtain a full-power account token, which UPC has not authorised. That should
wait for an agreement with UPC's Àrea TIC, as an LTI tool or a registered SSO client.

---

## 1. Summary table

| # | Data source | Data available | Access method | Auth required | Reliability | Legal risk | Effort |
|---|-------------|----------------|---------------|---------------|-------------|------------|--------|
| 1 | **Atenea calendar export** (Moodle core) | Assignment due dates, quiz open/close, course and site events, exam events if teachers add them. **No** weekly class timetable unless added as events. | Student generates an `.ics` URL in Atenea (Calendar → Export → "Get calendar URL") and pastes it | Secret token inside the URL (`userid` + `authtoken`), no password | High (core Moodle since 2.x) **[Verified: Moodle source]**; enabled at UPC **[Unverified: needs login]** | Low: student-initiated, documented feature | **S** (Novi already parses `.ics`) |
| 2 | **Atenea Moodle web services** (mobile app API) | Enrolled courses, course contents and files, calendar/action events, grades, forums, messages | Token from `admin/tool/mobile/launch.php` after UPC SSO in a browser; then REST calls | Full SSO login; token = full account power for the `moodle_mobile_app` service | Technically high: web services **enabled** **[Verified: observed]** | **High** without a UPC agreement: impersonates the official app, stores a bearer credential | **M** (tech) / **L** (with the agreement) |
| 3 | Atenea scraping with the student's password | Everything the student sees | Store UPC username + password, log in headlessly | Password | Low (2FA, SSO changes) | **Unacceptable**: breaks the UPC identity terms; excluded by the brief | — |
| 4 | **UPC LOGIN (SSO)** as an identity provider | Identity (who the student is), maybe basic attributes | OIDC / OAuth 2.0 / SAML 2 / CAS | UPC must register Novi as a client | High | Low **with** an agreement; impossible without | **L** (institutional) |
| 5 | **Visor d'Horaris UPC** (visorhoraris.upc.edu) | Public class timetables, groups, rooms, professors, teaching language, exam dates, link to the course guide | Public web app (JS); shareable URL of a selection; the internal JSON API is undocumented | None | Medium (undocumented internals) | Low–medium (public data; undocumented API) | **M** |
| 6 | **SIA, Campus del Baix Llobregat** (mitra.upc.es): **EETAC's** timetable system | Public class timetables and exam calendars per subject/group, professors, rooms | Public web form + "Exporta a format calendari" (**.ics / .csv**, Google Calendar subscription URL) | None | Medium (official export, legacy stack) | Low | **S–M** |
| 7 | **FIB API** (api.fib.upc.edu) | Public: subjects, timetables (ICS), course guides, exams. Private (OAuth 2.0): the student's own data | Documented REST API, `client_id` for public data, OAuth 2.0 for private data | App registration; OAuth consent for private data | High (documented, versioned) | Low (sanctioned, with terms) | **S–M**, FIB only |
| 8 | **Guies docents** (upc.edu/content/grau/guiadocent/pdf/…) | Syllabus/contents, objectives, evaluation, credits, languages, degrees | Public PDF per subject code and language | None | High (stable URL pattern, generated from PRISMA) | Low | **S** (Novi already ingests PDFs) |
| 9 | **School academic calendars** (e.g. EETAC) | Term dates, exam periods, non-teaching days | Public web page + PDF | None | High | Low | **S** |
| 10 | App UPC Estudiants | Personal timetable, published grades (with notifications) | Official app; no public API found | UPC login | — | Not accessible to third parties | — |
| 11 | UPC open-data portal | No academic dataset found (only Decidim participation data) | — | — | — | — | — |

---

## 2. Source by source

### 2.1 Atenea (Moodle): facts that apply to both routes

- Atenea is UPC's virtual campus, built on Moodle. It is used for bachelor's and master's degrees and
  "adapted to UPC's academic information systems". **[Verified]**
  [SGA: Plataforma ATENEA](https://www.upc.edu/sga/es/verifica/Recursos/Moodle)
- UPC officially tells students to use the **Moodle Mobile app** with site URL `atenea.upc.edu`.
  **[Verified]** [Serveis TIC: Atenea](https://serveistic.upc.edu/ca/atenea). The page says:
  "Descarrega't l'APP Moodle Mobile … URL del lloc moodle: atenea.upc.edu".
- Access requires "les credencials de la intranet de la UPC". **[Verified]** (same page)
- **Observed response** from the public mobile config, one unauthenticated call, no personal data:
  ```
  POST https://atenea.upc.edu/lib/ajax/service-nologin.php?info=tool_mobile_get_public_config
  → sitename: "Campus Virtual UPC"
    enablewebservices: 1
    enablemobilewebservice: 1
    typeoflogin: 2                 # 2 = LOGIN_VIA_BROWSER (tool_mobile\api)
    launchurl: https://atenea.upc.edu/admin/tool/mobile/launch.php
    identityproviders: [{name: "CAS", url: ".../login/index.php?authCAS=CAS"}]
    tool_mobile_qrcodetype: 2      # QR login enabled (type 2 = login QR)
    tool_mobile_androidappid: com.moodle.moodlemobile   # the official app
    tool_mobile_disabledfeatures: competencies/learning-plan blocks only
  ```
  **[Verified: observed 2026-09-26]**. The meaning of `typeoflogin` constants comes from the Moodle
  source (`admin/tool/mobile/classes/api.php`: 1 = app, 2 = browser, 3 = embedded browser).
  **[Verified]** [Moodle source](https://fossies.org/dox/moodle-5.1.5/admin_2tool_2mobile_2classes_2api_8php_source.html)
- Atenea transfers grades to PRISMA (since 2017) and feeds published grades to the App UPC
  Estudiants. **[Verified]** [Evolució del servei](https://serveistic.upc.edu/ca/atenea/el-servei/evolucio-del-servei),
  [App UPC Estudiants](https://serveistic.upc.edu/ca/atenea/documentacio/documentacio-de-referencia-1/app-upc-estudiants)

### 2.2 Atenea calendar export (`.ics`): the zero-password shortcut

**Evidence**
- Moodle's `calendar/export_execute.php` serves an iCalendar feed authenticated only by `userid` +
  `authtoken`. It sets `NO_MOODLE_COOKIES` (no session) and supports `preset_what` = all | user |
  groups | courses | categories and `preset_time` = weeknow … recentupcoming | custom. **[Verified:
  Moodle source]** [Moodle 5.2 source](https://fossies.org/dox/moodle-5.2.1/export__execute_8php.html)
- The token is derived per user (`calendar_get_export_token($user)`). It changes when the user's
  password changes, and the endpoint is off when `enablecalendarexport` is disabled. **[Verified:
  Moodle source]**
- An official EETAC page (from its EPSC era, ~2010) explains how to sync Atenea calendars into
  gCalendar/Outlook and says calendars update automatically. **[Verified that it existed]**
  [EETAC news 1148](https://eetac.upc.edu/ca/news/1148). **[Unverified]** that export is still
  enabled on Atenea today; this needs one look while logged in.

**What works**
- Novi's onboarding already accepts an `.ics` link or file. It parses weekly RRULE events, repeated
  one-off events and exam-like all-day events (`backend/app/onboarding/timetable.py::parse_ics`), and
  guards the link fetch against SSRF (`backend/app/onboarding/extract.py::fetch_ics`).
- With a periodic refresh, Atenea deadlines (assignment due, quiz close) could become feed cards:
  "Thermo lab report due Thursday — want me to draft an outline from your notes?".

**What doesn't**
- Atenea courses rarely contain the **weekly class timetable**. That comes from the school's
  timetable system (§2.5, §2.6). **[Unverified: depends on teachers]**
- Grades and files are not included.

**Unknowns (needs your login, with approval)**
- Is "Export calendar" visible for students on Atenea?
- Which event types appear, and how far ahead ("recentupcoming" ≈ 2 months in core)?

### 2.3 Atenea web services via the mobile SSO flow: "log in with UPC"

**How the flow works** **[Verified: Moodle docs/source + a Moodle core developer answer]**
1. The app opens `…/admin/tool/mobile/launch.php?service=moodle_mobile_app&passport=<random>&urlscheme=<scheme>`
   in a browser.
2. The student logs in at UPC's SSO (Atenea's identity provider is **CAS** behind **LOGIN UPC**).
3. `launch.php` issues a web-service token and redirects to `<scheme>://token=<base64(passport:::token:::privatetoken)>`.
4. The app then calls REST functions with that token.

The `urlscheme` parameter can be set by the caller unless the site forces one. **[Verified]**
[launch.php source](https://fossies.org/dox/moodle-5.2.1/admin_2tool_2mobile_2launch_8php_source.html),
[moodle.org forum answer](https://moodle.org/mod/forum/discuss.php?d=457600)

**Functions that would give us what we want.** All are exposed to the `moodle_mobile_app` service.
**[Verified]** [Web service API functions](https://docs.moodle.org/dev/Web_service_API_functions)
- Enrolled courses: `core_enrol_get_users_courses`, `core_course_get_enrolled_courses_by_timeline_classification`
- Contents and files: `core_course_get_contents` (includes file URLs, downloadable with the token)
- Deadlines: `core_calendar_get_action_events_by_timesort`, `core_calendar_get_calendar_events`
- Grades: `gradereport_user_get_grade_items`, `gradereport_overview_get_course_grades`

**Why it's a no-go without an agreement**
- **The token is full account power.** It can read everything and also *submit* assignments, post in
  forums and send messages. Storing it makes Novi a custodian of an institutional credential.
  **[Verified: service scope in docs]**
- **It impersonates an official client.** Novi would request tokens for the `moodle_mobile_app`
  service, which UPC enabled for the official Moodle app (`com.moodle.moodlemobile`). UPC has not
  authorised third-party clients, and I found no public statement either way. **[Unverified]**
- **UPC's identity terms:** "La identitat es personal … intransferible, les credencials … no es poden
  cedir a ningú". **[Verified]** [Condicions d'ús](https://serveistic.upc.edu/ca/identitatDigital/el-servei/condicions-us).
  This flow doesn't hand over the password, but it hands a delegated, unrevocable-by-UPC bearer token
  to a third party. That breaks the spirit of the terms. **[Unverified: legal interpretation]**
- **2FA** is being rolled out on LOGIN UPC, which would make any password-based variant brittle in any
  case. **[Verified]** [SSO FAQ / 2FA guides](https://serveistic.upc.edu/ca/sso/faq)

**Sanctioned alternatives**, both needing UPC:
- **LTI tool inside Atenea.** UPC Serveis TIC lists "Nova gestió d'eines externes LTI" (25/26).
  **[Verified]** [Atenea page menu](https://serveistic.upc.edu/ca/atenea). An LTI 1.3 tool gets course
  context from within Atenea with the institution's consent.
- **Registered SSO client of LOGIN UPC**, which supports OIDC, OAuth 2.0, SAML 2 and CAS. **[Verified]**
  [SSO: descripció del servei](https://serveistic.upc.edu/ca/sso/el-servei/descripcio-del-servei).
  This gives identity; data still needs a sanctioned feed.

### 2.4 Password-based scraping (excluded)

It requires storing the student's UPC password. **Flagged: not acceptable** (brief + UPC identity
terms). It also breaks with 2FA and CAS changes. Not investigated further.

### 2.5 Visor d'Horaris UPC (13 schools, not EETAC)

- It publishes class timetables and exam dates for UPC programmes, with groups, time slots, assigned
  rooms, class types, **professors**, teaching languages, a **link to the course guide** and exam
  dates. **[Verified]** [visorhoraris.upc.edu](https://visorhoraris.upc.edu/inici?grp=D86)
- Participating schools: **EEBE, EPSEB, EPSEM, EPSEVG, ESEIAAT, ETSAV, ETSECCPB, ETSETB, ETSEIB, FME,
  FNB, FOOT, FIB.** **EETAC is not listed.** **[Verified]** [Horaris UPC](https://serveistic.upc.edu/ca/horaris)
- Students can "Guarda un enllaç a la pàgina (URL) amb els horaris dels grups de les assignatures que
  triïs". **[Verified]** [Descripció del servei](https://serveistic.upc.edu/ca/horaris/el-servei/descripcio-del-servei)
- The site is a JavaScript app. Fetching the page returns an empty shell, so the data comes from an
  internal, **undocumented** API. **[Verified: observed empty HTML]**; API shape **[Unverified]**.
- I found no official `.ics` export for the Visor. **[Unverified]**
- **Best use:** the student shares their Visor URL. Novi renders it headlessly (or the student takes a
  screenshot) and runs it through the existing timetable reader. This is robust today because it goes
  through our deterministic grid parser, then vision.

### 2.6 SIA, Campus del Baix Llobregat: EETAC's timetables and exams

- It publishes "Horaris de classe i d'exàmens de l'EETAC" for 2026-1: all EETAC degrees, subject
  selection (up to 20), filters by professor, room and morning/afternoon, plus mid-term and final
  exam calendars. **[Verified]** [mitra.upc.es SIA](https://mitra.upc.es/SIA/INFOWEB_HORARIS.FILTRE01?w_codi_ue=300)
- There is an **"Exporta a format calendari"** utility with iCalendar (.ics) and CSV, and a URL that
  Google Calendar can subscribe to. It warns that timetables change, especially rooms at the start of
  the term. **[Verified]** [SIA export page](https://mitra.upc.es/SIA/INFOWEB_HORARIS_FORMAT.EXTRACCIO?v_param=INFOWEB.horariEspai_%241%24w_espai%3DC4-%242%24v_curs_quad%3D2017-2)
- **Best use for EETAC students:** "pick your subjects on SIA → copy the calendar link → paste it in
  Novi". Novi's `.ics` import already handles weekly events. The subscription URL format for a
  personal selection is **[Unverified]**.

### 2.7 FIB API (FIB only)

- It covers public FIB data (subjects, timetables, course guides, exams) and the user's own data. JSON
  is available for all resources and **ICS** for some. Public data needs a `client_id`; private data
  needs OAuth 2.0 with registered redirect URIs. **[Verified]** [API docs](https://api.fib.upc.es/v2/docs/main),
  [FIB page](https://www.fib.upc.edu/en/fib/it-services/fib-api)
- Terms: the FIB/Racó logo can't be used; the app must link to the API; "In no case will the username
  and password of the Racó be introduced in a third-party application". **[Verified]**
  [Terms](https://api.fib.upc.es/v2/docs/condicions)
- **Is there an equivalent at EETAC?** None found. EETAC uses SIA (§2.6). **[Verified absence in
  public docs]**; an internal API **[Unverified]**.
- It is a good model for what an institution-sanctioned integration looks like. It is **school-specific,
  not UPC-wide**.

### 2.8 Course guides (guies docents)

- Public PDFs at `https://www.upc.edu/content/grau/guiadocent/pdf/{ca|cat|es|en}/{subject_code}`, for
  example [230105](https://www.upc.edu/content/grau/guiadocent/pdf/cat/230105). They contain the unit,
  degrees, ECTS, languages, objectives, **contents (the syllabus)** and teaching methodology.
  **[Verified]** They are generated from PRISMA.
  [UPC comunicació: càrrega PRISMA](https://www.upc.edu/comunicacio/ca/intranet/guies-de-projectes/web-upc.-estudis-i-unitats/carrega-dades-prisma)
- A "professorat" section listing the responsible teacher is common in UPC guides. **[Unverified: not
  visible in the excerpts I read]**
- **Best use:** Novi already asks for the syllabus progressively (`syllabus_wanted` card). With the
  subject code, which the Visor, SIA and FIB API all show, Novi can fetch the guide itself and fill the
  syllabus. Course Memory then tracks pace against real units. Zero student effort, public data.

### 2.9 School calendars

EETAC publishes term calendars: teaching weeks s1–s15, exam periods, non-teaching days. **[Verified]**
[EETAC calendari 2026-27](https://eetac.upc.edu/ca/els-estudis/calendari-academic/curs-2026-2027).
Novi could offer "Use EETAC's term dates?" as a one-tap card. This removes the semester-dates question
entirely.

---

## 3. Best achievable onboarding per option

| Option | Student effort | What Novi gets | Status |
|--------|----------------|----------------|--------|
| **A. "Log in with UPC" → everything imported** (Moodle token or LTI/SSO agreement) | 0 steps beyond login | Courses, files, deadlines, grades | Needs a **UPC agreement**; without it, no-go (§2.3) |
| **B. Drop a timetable screenshot** (shipped in this release) | 1 drop + 1 tap | Weekly slots, rooms, professors | **Works today** for any school, no UPC dependency |
| **C. Paste your Atenea calendar link** | 1 paste (after finding "Export calendar" once) | Deadlines, quiz/exam events, course events | Works with today's `.ics` import; needs refresh + deadline cards (**S**) |
| **D. EETAC: paste your SIA calendar link** / **FIB: sign in with Racó (OAuth)** | 1 paste / 1 consent | Weekly slots (+ exams at FIB) | SIA: **S** (existing `.ics` path). FIB: **S–M** (OAuth client) |
| **E. Auto-fetch course guides** | 0 | Syllabus per subject | **S**, public PDFs |

Recommended combination: **B (or D) for the week, then C as a card on day 1 ("Want your Atenea
deadlines too? Paste your calendar link"), with E automatic.** That is still one step to first value,
with deadlines and syllabus arriving as progressive-disclosure cards.

---

## 4. Legal and policy

- **UPC identity terms.** Credentials are personal and non-transferable. **[Verified]** Anything that
  stores a UPC password is ruled out. Token-based delegation without UPC's consent is, at best, a grey
  area. **[Unverified: legal interpretation]**
- **FIB API terms** allow third-party apps under conditions (no logo, link back, never ask for Racó
  credentials). **[Verified]**
- **Moodle** is GPL software. Its web services are enabled per site by the institution, and access
  terms are set by UPC, not by Moodle. **[Verified: Moodle docs]**
- **GDPR / LOPDGDD (Spain).** **[Verified: regulation text; application to Novi is Unverified]**
  - For data the student brings themselves (timetable, calendar link, notes), Novi is the
    **controller**. The lawful basis is the contract with the student (Art. 6(1)(b)) or consent
    (Art. 6(1)(a)), with data minimisation (Art. 5(1)(c)) and appropriate security (Art. 32).
  - Grades are not special-category data (Art. 9), but they are sensitive in practice. Avoid
    importing them unless the student asks.
  - If UPC integrates Novi institutionally (LTI or SSO data feeds), UPC becomes the controller and
    Novi a **processor**, which requires a data-processing agreement (**Art. 28**). A DPIA (Art. 35)
    is likely if Novi profiles study behaviour at scale.
  - **International transfers.** Novi sends student content to LLM providers (Google, OpenAI) outside
    the EU. That requires valid transfer mechanisms (Art. 44–46: SCCs / EU–US Data Privacy Framework)
    and must be disclosed in the privacy notice. **This applies to the product today, independent of
    UPC.**
- **Formal agreement required for:** option A, any institutional data feed (Gestor d'Horaris/PRISMA
  exports), an LTI tool inside Atenea, and systematic use of undocumented endpoints (Visor internals)
  at scale. Personal use by a student of their own calendar link or public pages does not need one.
  **[Unverified: to confirm with UPC's data-protection office (Manual UPC de Protecció de Dades)]**

---

## 5. Generalisation: UPC-only or a reusable connector?

- Moodle has **147,369 registered sites** worldwide, and **Spain is #1 with 13,046 registered sites**.
  **[Verified]** [stats.moodle.org](https://stats.moodle.org/). Registration is voluntary, so the real
  number is higher. **[Verified: stated on the page]**
- **Calendar export (option C)** is core Moodle, with the same URL shape everywhere. A "paste your
  Moodle calendar link" connector is **reusable across universities** with no per-institution work,
  as long as the site hasn't disabled `enablecalendarexport`.
- **The mobile web-service flow (option A)** is also core Moodle, but *permission* is per institution.
  Login types, identity providers and forced URL schemes vary, as seen in `tool_mobile_get_public_config`.
  Reusable code, non-reusable legitimacy.
- **Timetable systems are institution-specific.** UPC alone has three: the Visor, SIA at CBL and the
  FIB API. Other universities use Universitas XXI, custom portals or PDFs. The **screenshot/PDF reader
  shipped in this release is the reusable connector for timetables.**

---

## 6. Go / no-go

| | Benefit | Cost | Risk | Decision |
|---|---|---|---|---|
| C. Atenea calendar link + deadline cards | High: deadlines drive proactive cards | S (1–2 days): store the URL encrypted (it's a bearer secret), a daily refresh job, map Moodle event types → assignments/exams, dedupe, an "Atenea" card | Token leakage (read-only calendar); export may be disabled at UPC | **GO**: first integration |
| E. Course-guide auto-fetch | Medium–high: syllabus without asking | S | URL pattern change | **GO** |
| D. SIA `.ics` (EETAC) / FIB API | Medium: an alternative to the screenshot for these schools | S / S–M | Legacy endpoints change; FIB-only | **GO later** (after C) |
| Visor d'Horaris internal API | Medium | M | Undocumented, may break; ToS unclear | **No-go**: use share-URL → screenshot instead |
| A. Atenea token via mobile SSO | Very high: zero-step onboarding, files, grades | M tech + L institutional | High: impersonation, full-power token, UPC terms | **No-go without an agreement.** Open a conversation with UPC Serveis TIC about an **LTI 1.3** tool or a registered SSO client |
| Password scraping | — | — | Unacceptable | **Never** |

**Smallest viable first integration.** "Paste your Atenea calendar link." One text field, already
supported by onboarding step 1 and by Schedule → Import. It needs:
1. storing the URL encrypted at rest, masked in the UI, never logged;
2. a daily `refresh_calendar` job;
3. mapping VEVENTs to `Assignment` / `Exam` rows, keyed by `UID` so updates stay idempotent;
4. an `atenea_deadline` card ("Lab report due Thu. Want an outline from your notes?").

### Unknowns that need your account (only with your explicit approval before any login)
1. Whether Atenea shows **Calendar → Export → Get calendar URL** to students, and which events it
   contains for your courses.
2. The **SIA** subscription-URL format for a personal subject selection (no login needed; it's a public
   form, but I didn't submit it in this pass).
3. Whether **App UPC Estudiants** exposes any export (calendar sync) of the personal timetable.
