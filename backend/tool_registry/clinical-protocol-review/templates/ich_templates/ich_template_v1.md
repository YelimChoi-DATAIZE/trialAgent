# ICH Clinical Trial Protocol Template Guide

## Purpose

This document provides a structured reference template for generating clinical trial protocols aligned with ICH Good Clinical Practice principles. The protocol generation agent must use this template as the primary structure when drafting a clinical trial protocol.

The generated protocol should be clear, concise, scientifically sound, ethically appropriate, and operationally feasible.

## General Instructions for the Protocol Generation Agent

When generating a clinical trial protocol:

1. Follow the section order defined in this template.
2. Use formal clinical and regulatory writing style.
3. Do not invent unavailable study information.
4. If required information is missing, mark it as `[To be specified]`.
5. Ensure that study objectives, endpoints, design, population, intervention, safety assessment, and statistical analysis are internally consistent.
6. Ensure that each section contains protocol-level details, not general explanations.
7. Use ICH-aligned terminology where applicable.
8. For oncology trials, clearly define disease setting, biomarker status, line of therapy, prior treatment, response assessment criteria, and safety monitoring.
9. For interventional trials, include treatment assignment, intervention details, visit schedule, efficacy assessment, safety assessment, and discontinuation criteria.
10. At the end of the generated protocol, include a brief “Protocol Completeness Check” table.

---

# Clinical Trial Protocol Structure

## 1. General Information

Include the following information:

* Protocol title
* Protocol number
* Version number and date
* Sponsor name
* Investigational product or intervention
* Study phase
* Indication
* Study sites or regions
* Principal investigator
* Sponsor medical monitor
* Regulatory identifier, if applicable
* Confidentiality statement

### Required Output Format

```markdown
## 1. General Information

**Protocol Title:** [To be specified]  
**Protocol Number:** [To be specified]  
**Version and Date:** [To be specified]  
**Sponsor:** [To be specified]  
**Investigational Product:** [To be specified]  
**Study Phase:** [To be specified]  
**Indication:** [To be specified]  
**Study Sites:** [To be specified]  
**Principal Investigator:** [To be specified]  
```

---

## 2. Background Information and Scientific Rationale

Describe:

* Disease background
* Current standard of care
* Unmet medical need
* Investigational product or intervention background
* Nonclinical and clinical evidence
* Rationale for study design
* Rationale for dose, regimen, and treatment duration
* Risk-benefit rationale

For oncology protocols, include:

* Cancer type and stage
* Molecular or biomarker-defined population
* Prior treatment context
* Existing clinical evidence for similar agents
* Expected clinical benefit and key risks

---

## 3. Trial Objectives and Purpose

Define the study purpose clearly.

Include:

* Primary objective
* Secondary objectives
* Exploratory objectives, if applicable

Each objective must map to one or more endpoints.

### Required Output Format

```markdown
## 3. Trial Objectives and Purpose

### 3.1 Primary Objective
- To evaluate [primary clinical purpose].

### 3.2 Secondary Objectives
- To assess [secondary purpose].
- To characterize [additional outcome].

### 3.3 Exploratory Objectives
- To explore [biomarker, subgroup, pharmacodynamic, or translational objective].
```

---

## 4. Trial Design

Describe:

* Overall study design
* Study phase
* Study type
* Randomization
* Blinding
* Control group
* Number of arms
* Treatment allocation ratio
* Estimated sample size
* Study duration
* Participant duration
* Study schema
* Key design rationale

For randomized trials, include:

* Randomization method
* Stratification factors
* Blinding and unblinding procedures

For single-arm trials, include:

* Justification for single-arm design
* Historical control or benchmark, if applicable

### Required Output Format

```markdown
## 4. Trial Design

This is a [phase], [randomized/single-arm], [open-label/double-blind], [multicenter/single-center] clinical trial designed to evaluate [intervention] in participants with [disease/condition].

Participants will be assigned to [study arm description]. The planned sample size is approximately [N] participants.

The overall study design is intended to support evaluation of [primary objective] while ensuring appropriate safety monitoring and operational feasibility.
```

---

## 5. Selection of Participants

Define the study population.

Include:

* Target population
* Inclusion criteria
* Exclusion criteria
* Screening procedures
* Eligibility confirmation
* Re-screening rules, if applicable

### 5.1 Inclusion Criteria

Examples:

1. Age ≥ [specified age].
2. Histologically or cytologically confirmed [disease].
3. Disease stage or clinical setting: [To be specified].
4. Biomarker status: [To be specified], if applicable.
5. ECOG performance status of [0–1 / 0–2].
6. Adequate organ function.
7. Measurable disease according to [RECIST 1.1 / other criteria], if applicable.
8. Ability to understand and sign informed consent.

### 5.2 Exclusion Criteria

Examples:

1. Prior treatment with [excluded therapy].
2. Active uncontrolled infection.
3. Uncontrolled central nervous system metastases, if applicable.
4. Clinically significant cardiovascular disease.
5. Pregnancy or breastfeeding.
6. Other malignancy requiring active treatment, unless allowed.
7. Any condition that may interfere with study participation or interpretation of results.

---

## 6. Withdrawal, Discontinuation, and Participant Replacement

Describe:

* Withdrawal of consent
* Discontinuation of study treatment
* Discontinuation from study follow-up
* Lost to follow-up procedures
* Replacement rules
* Criteria for stopping treatment
* Criteria for stopping the trial

Treatment discontinuation criteria may include:

* Disease progression
* Unacceptable toxicity
* Investigator decision
* Participant decision
* Pregnancy
* Protocol noncompliance
* Sponsor decision
* Death

---

## 7. Treatment and Interventions

Describe:

* Investigational product
* Comparator or control intervention
* Dose and regimen
* Route of administration
* Treatment cycle
* Dose modification rules
* Concomitant medications
* Prohibited medications
* Treatment compliance
* Drug storage and accountability

### Required Output Format

```markdown
## 7. Treatment and Interventions

Participants will receive [intervention name] at a dose of [dose] administered by [route] every [schedule] in [cycle length] cycles.

Treatment will continue until [disease progression / unacceptable toxicity / completion of planned treatment / withdrawal of consent / investigator decision].

Dose modifications, interruptions, or discontinuations will be performed according to protocol-defined safety criteria.
```

---

## 8. Assessment of Efficacy

Describe:

* Primary efficacy endpoint
* Secondary efficacy endpoints
* Exploratory efficacy endpoints
* Assessment schedule
* Assessment method
* Response criteria
* Central review or investigator assessment, if applicable

For oncology trials, consider:

* ORR
* DoR
* DCR
* PFS
* OS
* pCR
* EFS
* DFS
* RECIST 1.1
* iRECIST, if immunotherapy
* ctDNA or biomarker response, if applicable

Each efficacy endpoint must be linked to an objective.

---

## 9. Assessment of Safety

Describe:

* Safety endpoints
* Adverse event collection
* Serious adverse events
* Adverse events of special interest
* Laboratory assessments
* Vital signs
* Physical examination
* ECG or cardiac monitoring
* Pregnancy testing
* Dose-limiting toxicity, if applicable
* Safety review committee or DSMB, if applicable

Use standard terminology:

* Adverse events should be graded using CTCAE, if applicable.
* Serious adverse events should be collected and reported according to applicable regulatory requirements.

---

## 10. Statistical Considerations

Include:

* Analysis objectives
* Analysis populations
* Sample size justification
* Primary endpoint analysis
* Secondary endpoint analysis
* Exploratory analysis
* Interim analysis, if applicable
* Multiplicity adjustment, if applicable
* Missing data handling
* Subgroup analysis
* Sensitivity analysis
* Statistical software

### Analysis Populations

Define as applicable:

* Intent-to-treat population
* Full analysis set
* Per-protocol population
* Safety population
* Pharmacokinetic population
* Biomarker-evaluable population

### Estimand Considerations

Where applicable, define:

* Treatment condition
* Target population
* Endpoint or variable
* Intercurrent events
* Population-level summary measure

---

## 11. Direct Access to Source Records and Documents

Describe:

* Investigator responsibility to provide access to source documents
* Sponsor monitoring access
* Regulatory authority inspection access
* IRB/IEC access, if applicable
* Confidentiality protection

---

## 12. Quality Control and Quality Assurance

Describe:

* Monitoring plan
* Risk-based quality management
* Protocol deviation management
* Data quality review
* Source data verification or source data review
* Audit and inspection readiness
* Vendor and CRO oversight, if applicable

The protocol should identify factors critical to participant safety, rights, and data reliability.

---

## 13. Ethics and Regulatory Considerations

Include:

* Ethical conduct statement
* IRB/IEC approval
* Informed consent process
* Participant confidentiality
* Risk-benefit assessment
* Vulnerable populations, if applicable
* Clinical trial registration
* Compliance with applicable laws and regulations

### Required Statement

```markdown
The study will be conducted in accordance with the principles of Good Clinical Practice, applicable regulatory requirements, and ethical principles that have their origin in the Declaration of Helsinki.
```

---

## 14. Data Handling and Record Keeping

Describe:

* Data collection method
* Electronic data capture system
* Source data
* Data entry and validation
* Query management
* Data privacy
* Record retention
* Database lock
* Data transfer, if applicable

If digital tools, decentralized elements, wearables, or external data sources are used, describe:

* Data flow
* Data provenance
* Data integrity controls
* System validation
* Access control

---

## 15. Financing and Insurance

Describe:

* Study funding source
* Sponsor responsibilities
* Insurance or indemnity
* Compensation for study-related injury, if applicable

If unknown, write `[To be specified]`.

---

## 16. Publication Policy

Describe:

* Publication rights
* Authorship principles
* Sponsor review process
* Timing of publication
* Clinical trial result disclosure
* Data sharing statement, if applicable

---

# Protocol Completeness Check

At the end of the generated protocol, include the following checklist:

```markdown
## Protocol Completeness Check

| Area | Status | Notes |
|---|---:|---|
| Study title and version | Complete / Missing |  |
| Scientific rationale | Complete / Missing |  |
| Primary objective | Complete / Missing |  |
| Primary endpoint | Complete / Missing |  |
| Study design | Complete / Missing |  |
| Target population | Complete / Missing |  |
| Inclusion/exclusion criteria | Complete / Missing |  |
| Intervention details | Complete / Missing |  |
| Efficacy assessments | Complete / Missing |  |
| Safety assessments | Complete / Missing |  |
| Statistical analysis plan summary | Complete / Missing |  |
| Ethics and informed consent | Complete / Missing |  |
| Data handling | Complete / Missing |  |
| Quality management | Complete / Missing |  |
```

---

# Internal Consistency Rules for the Agent

The protocol generation agent must check the following before finalizing the protocol:

1. The primary objective must match the primary endpoint.
2. The study population must match the indication.
3. Inclusion and exclusion criteria must not contradict each other.
4. The efficacy assessment schedule must support the endpoint analysis.
5. The safety monitoring plan must be appropriate for the intervention risk.
6. The sample size rationale must match the primary endpoint and study design.
7. The statistical analysis population must be defined.
8. Randomization and blinding must be described if applicable.
9. Dose modification rules must be included for drug intervention trials.
10. Missing or unavailable information must be marked as `[To be specified]`.

---

# Recommended Output Style

The generated protocol should be written in formal regulatory language.

Avoid:

* Promotional claims
* Unsupported efficacy statements
* Overly vague eligibility criteria
* Unexplained endpoints
* Inconsistent terminology
* Hallucinated regulatory identifiers
* Unspecified treatment schedules

Use:

* Clear section headings
* Precise clinical terminology
* Consistent endpoint definitions
* Traceability between objectives and endpoints
* Structured tables where appropriate
* `[To be specified]` for missing information
