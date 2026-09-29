"""
In-app help content: the per-page "About this page" drawer and the full User Manual.

One entry per login role (`session['role']`, uppercase). A role with no entry simply gets no
help button and no manual link, so roles can be added one at a time.

`sections` is keyed by the dashboard section id (the `nav-…` ids in `app/templates/<role>_dashboard.html`
and `app/navigation.py`). The drawer looks up whichever section is currently active, so a renamed
or added dashboard section needs the same change here -- nothing links the two.

Everything is plain text (no HTML): both the drawer and the manual page render it as text.

Section fields:
    title    heading shown in the drawer / manual chapter
    purpose  one or two sentences: what this page is for
    steps    ordered "what to do here" list
    tips     optional "good to know" list
"""

def _leader_ipcr_sections(core_note, self_issued=False):
    """
    Help for the shared /designated/ "My IPCR" pages as seen by a Program Chair, RET Chair or Dean.

    Their IPCR is formulated and pre-approved by the Dean rather than drafted by them, so it
    differs from plain Designated Faculty. `core_note` is the one role-specific sentence: who
    distributes their Instruction share. `self_issued` is for the Dean, who formulates and issues
    their own IPCR from Target Assignment rather than receiving it.
    """
    if self_issued:
        purpose = (
            "Your own personal IPCR, separate from the reviews you do for others. You formulate "
            "it yourself from Target Assignment and issue it to yourself already approved. Your "
            "job here is to check it and lock it."
        )
        waiting_step = "If you see Waiting for the Dean to formulate your Draft IPCR, you have not issued your own yet. Open Target Assignment, click Draft IPCR on your own row and choose Save & Issue Draft IPCR."
        return_step = "If your IPCR is returned, re-issue it from Target Assignment. You cannot change it on this page."
    else:
        purpose = (
            "Your own personal IPCR, separate from the reviews you do for others. The Dean "
            "formulates it for you and issues it already approved, so there is nothing to "
            "draft. Your job here is to check it and lock it."
        )
        waiting_step = "If you see Waiting for the Dean to formulate your Draft IPCR, the Dean has not issued it yet. Check back later."
        return_step = "If the Dean returns your IPCR, you cannot change it yourself. The Dean re-formulates and issues it again."
    evidence_tip = (
        "Your own evidence lands in your own Evidence Verification queue, because nobody else is positioned to review it."
        if self_issued else
        "Your own evidence goes straight to the Dean. No other chair is positioned to review it."
    )
    return {
        'designated-dpcr': {
            'title': 'My IPCR',
            'purpose': purpose,
            'steps': [
                waiting_step,
                "Core Functions shows your teaching load and the instruction allocated to you. " + core_note,
                "Strategic Priorities & Support Functions shows your departmental oversight targets. Their quantities are fixed by the Dean's cascade.",
                "When the banner says your IPCR was formulated and pre-approved by the Dean, read the Dean's remarks if any and check the targets.",
                "Click Lock My IPCR to commit your targets and open Evidence Gathering. If your Core Functions are not complete yet, the banner tells you what is missing and locking waits for it.",
                return_step,
            ],
            'tips': [
                "Use the sidebar links to jump back to your own dashboard at any time. They return you to the same section.",
                "Locking is final for the term.",
            ],
        },
        'nav-evidence': {
            'title': 'Evidence Gathering (My IPCR)',
            'purpose': (
                "After you lock your own IPCR, report your accomplishments and upload proof for "
                "your own targets, just like any faculty member."
            ),
            'steps': [
                "Open a target in My Evidence Submission Checklist to add its evidence.",
                "Upload your proof as a PDF (maximum 10 MB).",
                "Fill in Accomplishment Details: Completed in (used for your Timeliness rating), the completion status, and the Client Satisfaction Rating where asked.",
                "Departmental oversight rows get their quantity worked out from your department's verified evidence. You cannot upload a number for them, but you still state when the department finished, which drives Timeliness.",
                "When every target has its evidence, click Submit Evidences.",
            ],
            'tips': [
                evidence_tip,
                "Once submitted, the page is locked unless something is returned to you.",
            ],
        },
        'nav-print-ipcr': {
            'title': 'Print IPCR (My IPCR)',
            'purpose': "A read-only view of your own official IPCR, laid out like the standard SPMS form, ready to print.",
            'steps': [
                "Review the table of targets, accomplishments and ratings.",
                "Click View & Print to open the printable form in a new tab, then use your browser's Print.",
            ],
            'tips': [
                "Your Summary of Ratings uses the Designated Faculty weights (25% Core Functions, 75% Strategic Priorities & Support Functions).",
                "Before final approval, this page shows your approved commitment only. Ratings fill in after the evaluation.",
            ],
        },
    }


HELP = {
    'FACULTY': {
        'label': 'Faculty Member',
        'home_endpoint': 'faculty.faculty_dashboard',
        'intro': (
            "D-IPCR replaces the paper IPCR with a guided online process. Instead of writing your "
            "own targets from scratch, your Dean, Program Chair and RET Chair set up your targets "
            "for you, you review and submit them, then later you upload proof of what you "
            "accomplished. This manual walks you through each step."
        ),
        'journey': [
            ('Review your targets', "Your Program Chair and RET Chair assign your teaching, support, research and extension targets. You open My IPCR and check them."),
            ('Choose your Research (if it applies)', "If your rank has a Research menu, you tick the research targets you will commit to."),
            ('Submit for approval', "You send the draft IPCR to your reviewers. The RET Chair checks Research and Extension first, then the Program Chair checks everything."),
            ('Fix anything that is returned', "If a reviewer returns your draft, read the remarks, adjust, and resubmit."),
            ('Lock your IPCR', "Once approved, you lock it. Your targets become your official commitment and can no longer be edited."),
            ('Gather evidence', "Through the term, you report what you accomplished and upload a PDF proof for each target."),
            ('Submit evidence for verification', "Your chairs verify the proof and the Dean gives the final approval."),
            ('Print your IPCR', "After final approval, you can print the official IPCR form with your ratings."),
        ],
        'sections': {
            'nav-overview': {
                'title': 'Overview',
                'purpose': (
                    "Your starting page. It shows who you are in the system, which term is open, "
                    "and where your IPCR currently stands."
                ),
                'steps': [
                    "Check that your Rank and Specialization in My Profile are correct. Targets are assigned based on them, so tell the Administrator if either is wrong.",
                    "Check the Current Term card. If it says No Active Term, the Administrator has not opened a term yet and you cannot start.",
                    "Read the banner under the cards for your status, for example approved and locked, or finalized by the Dean.",
                    "Use the sidebar to move to My IPCR, Evidence Gathering and Print IPCR.",
                ],
                'tips': [
                    "Evidence Gathering appears in the sidebar only after your IPCR is locked. Print IPCR appears once it is locked or finalized.",
                ],
            },
            'nav-ipcr': {
                'title': 'My IPCR',
                'purpose': (
                    "Where you prepare your draft IPCR for the term. You review the targets "
                    "assigned to you, choose your Research targets if your rank allows it, submit "
                    "for approval, and finally lock the approved IPCR."
                ),
                'steps': [
                    "Strategic Priorities lists your teaching (Instruction) targets, and Support Functions lists your support targets. Both are assigned by your Program Chair and cannot be edited by you.",
                    "Research Menu (only if you are eligible): tick the research targets you will commit to, up to the number required for your academic rank. A target the RET Chair assigned to you directly is already locked in.",
                    "Extension Targets are set by the RET Chair for your rank and are shown read-only. You do not select them.",
                    "If the Draft IPCR Submission Unavailable notice appears, your chairs have not finished assigning your baseline targets. The checklist shows which items are still Pending. Come back once they read Ready.",
                    "Click Submit IPCR for Approval. Research and Extension go to the RET Chair first, then everything goes to the Program Chair.",
                    "If your draft is Returned, read the remarks shown in red or orange and any per-target notes, adjust it, and submit again.",
                    "When both chairs approve, click Lock My IPCR. This makes your targets official.",
                ],
                'tips': [
                    "You cannot edit anything while your draft is waiting for review. Wait for the decision.",
                    "Locking is final for the term. Check your targets carefully before you lock.",
                    "If you have no Research menu, you go straight to the Program Chair. That is normal for your rank.",
                ],
            },
            'nav-evidence': {
                'title': 'Evidence Gathering',
                'purpose': (
                    "After your IPCR is locked, this page is where you report what you actually "
                    "accomplished for each target and upload proof. Your chairs verify it and the "
                    "Dean gives final approval."
                ),
                'steps': [
                    "Find a target in the table and click Add/View Evidence.",
                    "Fill in the Actual Accomplishment (how many you completed), the Completed in field, and the Client Satisfaction Rating where asked. Add a short note if you want it printed in the Remarks column of your IPCR.",
                    "Upload your proof as a PDF (maximum 10 MB). Other file types are rejected.",
                    "Watch the Q, E, T and A columns and the category summary below the table. They update live as you report.",
                    "When every target has its evidence, click Submit Evidences for Verification.",
                    "If a target is marked in red, your evidence was returned. Open it, read the reason, replace the file or correct the details, then click Resubmit Evidences for Verification.",
                ],
                'tips': [
                    "If a target is below its committed quantity, the system warns you but still lets you submit.",
                    "Your Program Chair verifies the evidence for all of your targets, including Research and Extension. The RET Chair can see it but does not approve or return it.",
                    "Use one clear PDF per piece of proof, and keep file names recognizable to you.",
                ],
            },
            'nav-print-ipcr': {
                'title': 'Print IPCR',
                'purpose': (
                    "A read-only view of your official IPCR, laid out like the standard SPMS form, "
                    "ready to print."
                ),
                'steps': [
                    "Review the table of targets, accomplishments and ratings.",
                    "Click the print button to open the printable form in a new tab, then use your browser's Print.",
                    "Choose landscape orientation if your browser does not pick it automatically.",
                ],
                'tips': [
                    "Before final approval, this page shows your approved commitment only. Ratings fill in after the evaluation.",
                    "Once the Dean has approved, the page says Finalized IPCR and the ratings and Final Weighted Rating are complete.",
                ],
            },
        },
        'glossary': [
            ('IPCR', "Individual Performance Commitment and Review. The form that records what you committed to do and what you accomplished."),
            ('Target', "A single commitment on your IPCR, for example a teaching load or a research output, with a quantity."),
            ('Program Chair', "Assigns your teaching and support targets and reviews your draft and your evidence."),
            ('RET Chair', "Research, Extension and Training Chair. Sets your Research menu and Extension targets and reviews that part of your IPCR."),
            ('Dean', "Gives the final approval of your evidence and IPCR."),
            ('Locked', "Your approved targets are now your official commitment and cannot be edited."),
            ('Returned', "A reviewer sent your submission back with remarks. Fix it and submit again."),
            ('Q, E, T, A', "Ratings computed by the system for each target, and their average. They roll up into your Final Weighted Rating."),
        ],
        'faq': [
            ('The Submit button is disabled. Why?', "Your Program Chair or RET Chair has not finished assigning your baseline targets. The checklist on My IPCR shows what is Pending."),
            ('I do not see Evidence Gathering.', "It appears only after you lock your IPCR. Lock it from My IPCR once both chairs have approved."),
            ('I made a mistake after locking.', "Locked targets cannot be edited. Contact your Program Chair to discuss it."),
            ('My Rank or Specialization is wrong.', "Ask the system Administrator to correct your profile. Your targets depend on it."),
            ('My PDF will not upload.', "Only PDF files up to 10 MB are accepted. Compress or re-export the file and try again."),
        ],
    },

    'DESIGNATED_FACULTY': {
        'label': 'Designated Faculty',
        'home_endpoint': 'designated.designated_dashboard',
        'intro': (
            "As a Designated Faculty member you carry administrative duties on top of teaching, so "
            "your IPCR is built differently from a Regular Faculty member's. Your teaching load and "
            "the instruction your Program Chair assigns are your Core Functions. You pick the rest "
            "of your targets yourself, and the Dean is your reviewer. This manual walks you "
            "through each step."
        ),
        'journey': [
            ('Review your Core Functions', "Your mandatory teaching load and any instruction your Program Chair distributed to you are already listed and locked."),
            ('Choose your other targets', "From the pool of available targets you tick the ones you will take on, and set the quantity and deadline for each."),
            ('Add custom targets if needed', "If your duties include something not in the pool, add it as a custom target."),
            ('Submit to the Dean', "You send the draft IPCR to the Dean. The Dean may adjust quantities and add notes."),
            ('Fix anything that is returned', "If the Dean returns your draft, read the remarks, adjust, and resubmit."),
            ('Lock your IPCR', "Once the Dean approves, you lock it and your targets become your official commitment."),
            ('Gather evidence', "Through the term, you report what you accomplished and upload a PDF proof for each target."),
            ('Submit evidence for verification', "Your Program Chair checks the proof and passes it to the Dean, who gives the final approval."),
            ('Print your IPCR', "After final approval, you can print the official IPCR form with your ratings."),
        ],
        'sections': {
            'designated-overview': {
                'title': 'Overview',
                'purpose': "Your starting page. It shows your rank, your designation and which term is open.",
                'steps': [
                    "Check that your Rank and Designation are correct. Your targets and your rating weights depend on them, so tell the Administrator if either is wrong.",
                    "Check the Current Term card. If it says No Active Term, the Administrator has not opened a term yet and you cannot start.",
                    "Use the sidebar to move to My IPCR, Evidence Gathering and Print IPCR.",
                ],
                'tips': [
                    "Evidence Gathering appears in the sidebar only after your IPCR is locked. Print IPCR appears once it is locked or finalized.",
                ],
            },
            'designated-dpcr': {
                'title': 'My IPCR',
                'purpose': (
                    "Where you prepare your IPCR for the term. Your teaching and assigned "
                    "instruction come pre-filled, you choose or add the rest, then send everything "
                    "to the Dean for approval."
                ),
                'steps': [
                    "Core Functions lists your mandatory teaching load and any instruction your Program Chair distributed to you. These are locked and you cannot change them.",
                    "Strategic Priorities & Support Functions is where your other targets go. Tick Select on each pool target you will take on.",
                    "For each selected target, set the Target Qty and the Deadline (a number and a unit such as months). The description fills in automatically and shows an Auto badge. You may type over it, and Reset to Auto brings the standard wording back.",
                    "Need something that is not in the pool? Click Add Target, choose the type, then enter a description, quantity and Target Duration. Custom targets are always free text.",
                    "Click Submit IPCR for Approval. The Dean reviews it under IPCR Draft Approval.",
                    "If the Dean returns it, the banner shows the Dean's remarks and a Dean's note may appear on individual targets. Your targets become editable again. Make the changes and click Re-submit IPCR for Approval.",
                    "When the Dean approves, click Lock My IPCR to commit your targets and move on to evidence gathering.",
                ],
                'tips': [
                    "The Dean may change a quantity or deadline while reviewing. Look at the final numbers before you lock.",
                    "A target tagged Departmental Oversight, Auto-linked, has its total worked out by the system from your department's accomplishments. You do not upload evidence for it yourself.",
                    "After you submit, you cannot edit until the Dean decides.",
                    "Locking is final for the term. Check your targets carefully first.",
                ],
            },
            'nav-evidence': {
                'title': 'Evidence Gathering',
                'purpose': (
                    "After your IPCR is locked, this page is where you report what you actually "
                    "accomplished for each target and upload proof."
                ),
                'steps': [
                    "Open a target in the My Evidence Submission Checklist to add its evidence.",
                    "Upload your proof as a PDF (maximum 10 MB). Other file types are rejected.",
                    "Fill in Accomplishment Details: how many you completed, Completed in (used for your Timeliness rating), the completion status, and the Client Satisfaction Rating where the target asks for one. Add a short remark if you want it printed on your IPCR.",
                    "Watch the Q, E, T badges update as you save your details.",
                    "When every target has its evidence, click Submit Evidences. You are warned if a target is below its committed quantity, but you may still submit.",
                    "If a target comes back marked as returned, open it, fix the file or details, and submit again.",
                ],
                'tips': [
                    "Your evidence goes to your Program Chair first. They verify your files and then submit the package to the Dean, so it can take a while to reach the Dean.",
                    "Once you have submitted, the page is locked until something is returned to you.",
                ],
            },
            'nav-print-ipcr': {
                'title': 'Print IPCR',
                'purpose': (
                    "A read-only view of your official IPCR, laid out like the standard SPMS form, "
                    "ready to print."
                ),
                'steps': [
                    "Review the table of targets, accomplishments and ratings.",
                    "Click View & Print to open the printable form in a new tab, then use your browser's Print.",
                    "Choose landscape orientation if your browser does not pick it automatically.",
                ],
                'tips': [
                    "Before final approval, this page shows your approved commitment only. Ratings fill in after the evaluation.",
                    "Your Summary of Ratings uses the Designated Faculty weights (25% Core Functions, 75% Strategic Priorities & Support Functions), not the Regular Faculty weights.",
                ],
            },
        },
        'glossary': [
            ('IPCR', "Individual Performance Commitment and Review. The form that records what you committed to do and what you accomplished."),
            ('Core Functions', "Your teaching load and the instruction your Program Chair assigns you. Locked, and worth 25% of your rating."),
            ('Strategic Priorities & Support Functions', "Everything else you take on: pool targets, custom targets and oversight duties. Worth 75% of your rating."),
            ('Pool target', "A target defined by the Administrator that you may choose to take on."),
            ('Custom target', "A target you write yourself when nothing in the pool fits your duties."),
            ('Program Chair', "Distributes instruction to you and verifies your evidence before it goes to the Dean."),
            ('Dean', "Reviews and approves your draft IPCR, and gives the final approval of your evidence."),
            ('Locked', "Your approved targets are now your official commitment and cannot be edited."),
            ('Returned', "A reviewer sent your submission back with remarks. Fix it and submit again."),
            ('Q, E, T', "Ratings computed by the system for each target. They roll up into your Final Weighted Rating."),
        ],
        'faq': [
            ('Why is my teaching load fixed?', "Teaching load is mandatory for Designated Faculty and its hours are set by the Administrator. You cannot change it."),
            ('My Core Functions has no instruction from my Program Chair.', "Only the teaching load is guaranteed. Instruction appears when your Program Chair distributes it to you. Ask them if you expected some."),
            ('I do not see Evidence Gathering.', "It appears only after you lock your IPCR. Lock it from My IPCR once the Dean has approved."),
            ('The Dean has not seen my evidence yet.', "Your Program Chair reviews it first and then submits it to the Dean. Check with them."),
            ('My Rank or Designation is wrong.', "Ask the system Administrator to correct your profile."),
            ('My PDF will not upload.', "Only PDF files up to 10 MB are accepted. Compress or re-export the file and try again."),
        ],
    },

    'PROGRAM_CHAIR': {
        'label': 'Program Chair',
        'home_endpoint': 'prog_chair.prog_chair_dashboard',
        'intro': (
            "As Program Chair you turn the Dean's college-wide quotas into concrete targets for "
            "the faculty in your department, then review what they submit and the evidence they "
            "gather. You also have a personal IPCR of your own, which the Dean prepares for you. "
            "This manual walks you through each step."
        ),
        'journey': [
            ('Allocate baseline targets', "In Target Allocation you split the Dean's quotas for your department across your faculty, then finalize."),
            ('Wait for faculty to submit', "Once your allocation is final, faculty prepare their draft IPCRs. Regular Faculty with Research go through the RET Chair before you."),
            ('Review draft IPCRs', "In Commitments you check each draft, adjust quantities if needed, and approve it or return it with remarks."),
            ('Faculty lock their IPCR', "Approved faculty lock their IPCRs. That opens their evidence gathering."),
            ('Verify evidence', "In Evidence Verification you check each uploaded file for teaching and support targets and approve or return it."),
            ('Send verified packages to the Dean', "Once a Regular Faculty member's evidence is fully approved, you submit it to the Dean for final approval."),
            ('Lock and evidence your own IPCR', "Lock your own IPCR when the Dean issues it, then report your own accomplishments. Your evidence goes straight to the Dean."),
        ],
        'sections': {
            'nav-overview': {
                'title': 'Overview',
                'purpose': "A snapshot of your department for the current term.",
                'steps': [
                    "Active Faculty shows how many faculty are under your specialization.",
                    "Pending Drafts is how many draft IPCRs are waiting for your review. The same number shows as a red badge on Commitments in the sidebar.",
                    "Approved IPCRs is how many drafts you have approved this term.",
                    "Use the sidebar to open Target Allocation, Commitments and Evidence Verification, or My IPCR for your personal IPCR.",
                ],
                'tips': [
                    "The Target Allocation card shows a fixed 100% figure. Open Target Allocation itself to see whether you have actually finalized your allocation.",
                ],
            },
            'nav-phase1': {
                'title': 'Target Allocation',
                'purpose': (
                    "Where you distribute the Dean's quotas for your department to each faculty "
                    "member. This is the baseline every faculty member's IPCR is built from."
                ),
                'steps': [
                    "Strategic Priorities and Support Functions each list the master indicators the Dean cascaded to your department, with the Dept Quota for each.",
                    "For every indicator, enter the amount each faculty member will receive in Assigned Per Faculty, and a Deadline as a number plus a unit.",
                    "Click Auto Divide Section, or Auto Divide All Targets at the top, to split each department quota by your number of faculty, rounded up. You can still edit the results.",
                    "The IPCR Target Description (Faculty Version) fills in automatically as you type and shows an Auto badge. If you type over it, the badge disappears and Reset to Auto brings the standard wording back.",
                    "Check Total Distributed against the Dept Quota for each row.",
                    "Click Save Targets, then confirm with Yes, Save & Finalize.",
                ],
                'tips': [
                    "Finalizing is one-way. Once saved, the page is locked for the term and shows Targets Finalized.",
                    "Faculty cannot submit their drafts until you have finished this step and the RET Chair has finished theirs. That is why they may ask you about it.",
                    "Instruction targets go to every faculty member in your department, including the Dean, the RET Chair, yourself and any other designated faculty. Support Functions go to Regular Faculty only.",
                    "Allocating Instruction to yourself is what completes your own Core Functions. You need it before you can lock your own IPCR.",
                ],
            },
            'nav-phase2': {
                'title': 'Commitments',
                'purpose': (
                    "Where you review the draft IPCRs your faculty submit, and approve them or "
                    "send them back."
                ),
                'steps': [
                    "Pending Draft Submissions lists the faculty whose drafts are waiting. Use Search faculty to find someone.",
                    "Click Review to open the draft. Under Proposed Targets you see every target: teaching load, Instruction, Support, Research and Extension.",
                    "You may adjust quantities on your own targets. Research and Extension were already checked by the RET Chair and are marked as approved by them.",
                    "Add remarks explaining your changes. Remarks are optional when approving. Explain your reasons when returning.",
                    "Click Approve IPCR to let the faculty member lock their IPCR, or Return to Faculty to send it back for changes.",
                    "A faculty member you returned shows as Awaiting Resubmission. When they resubmit, they return to your Pending queue.",
                    "Approved & Locked IPCRs lists faculty who have finished locking. Click View to see their committed targets.",
                ],
                'tips': [
                    "For Regular Faculty with Research or Extension, the RET Chair must approve first. Their drafts appear in your queue only after that.",
                    "A returned faculty member keeps their approved Research choice. It does not go back to the RET Chair.",
                    "Once a faculty member locks their IPCR, it can no longer be changed.",
                ],
            },
            'nav-evidence-verification': {
                'title': 'Evidence Verification',
                'purpose': (
                    "Where you verify all the evidence your Regular Faculty upload, including "
                    "Research and Extension, and pass approved packages on to the Dean. The RET "
                    "Chair can watch progress on Research and Extension but does not approve it."
                ),
                'steps': [
                    "Department Accomplishment Summary compares the quota cascaded to your department with the accomplishment you have already approved, per indicator.",
                    "Under Faculty Evidence Submissions, click View Evidences on a faculty member marked Evidences Submitted.",
                    "For each target you see what was reported, such as Completed in, the Client Satisfaction rating, and the Q, E, T badges, plus the uploaded files.",
                    "Click View Uploaded Evidence to open the file full screen, then Approve or Return it.",
                    "Returning a file requires a reason. The faculty member sees it and can upload a replacement for that target only.",
                    "When all of a Regular Faculty member's evidence is approved, they appear under Approved Regular Faculty Evidences. Click Submit to Dean to forward the package.",
                ],
                'tips': [
                    "Submit to Dean is final for that package. The Dean sees the faculty member only after you submit.",
                    "Once you decide on a file, its buttons disappear. Check carefully before you click.",
                    "Your own evidence and that of the RET Chair and the Dean does not come through this queue. Yours goes straight to the Dean.",
                ],
            },
            **_leader_ipcr_sections(
                "As Program Chair, your Instruction share comes from your own Target Allocation. Allocate it to yourself there first."
            ),
        },
        'glossary': [
            ('IPCR', "Individual Performance Commitment and Review. The form that records what a person committed to do and what they accomplished."),
            ('Quota', "The number the Dean assigns to your department for an indicator. You divide it among your faculty."),
            ('Master indicator', "A standard target defined by the Administrator, such as a teaching or extension output."),
            ('Departmental Oversight', "Your own targets for the whole department's total, worked out from the Dean's cascade. The system fills in the quantity from verified evidence."),
            ('Core Functions', "For you, your teaching load and the instruction allocated to you. Worth 25% of your own rating."),
            ('RET Chair', "Research, Extension and Training Chair. Reviews Research and Extension targets before you review the draft, and monitors that evidence read-only."),
            ('Dean', "Prepares your personal IPCR and gives the final approval of evidence."),
            ('Finalized', "Saved and locked. It cannot be changed for the term."),
            ('Returned', "Sent back with remarks so the faculty member can fix and resubmit."),
            ('Q, E, T', "Ratings computed by the system for each target. They roll up into a Final Weighted Rating."),
        ],
        'faq': [
            ('Faculty say they cannot submit their draft.', "Your Target Allocation is probably not finalized yet, or the RET Chair has not finished theirs. Finalize yours first."),
            ('I saved my allocation with a mistake.', "Finalized allocations cannot be edited. Contact the system Administrator."),
            ('A faculty draft is not in my Pending list.', "If they have Research or Extension, the RET Chair must approve first. Ask them to check with the RET Chair."),
            ('Do I verify Research and Extension evidence too?', "Yes. You approve or return all of a Regular Faculty member's evidence. The RET Chair only monitors the Research and Extension part."),
            ('The Dean does not see a faculty member yet.', "Approve all of their files, then click Submit to Dean under Approved Regular Faculty Evidences."),
            ('I cannot lock my own IPCR.', "Your Instruction share may not be allocated to you yet. Do that in Target Allocation, then come back."),
        ],
    },

    'RET_CHAIR': {
        'label': 'RET Chair',
        'home_endpoint': 'ret_chair.ret_chair_dashboard',
        'intro': (
            "As RET Chair you look after Research and Extension for the whole college. You decide "
            "which Research and Extension targets each academic rank sees, you can assign Research "
            "directly to individual faculty, and you review the Research and Extension part of "
            "each faculty draft before the Program Chair sees it. You also have a personal IPCR "
            "of your own, which the Dean prepares for you. This manual walks you through each step."
        ),
        'journey': [
            ('See what the Dean cascaded to RET', "Cascaded Targets shows the Research and Extension quotas the Dean gave your unit."),
            ('Configure the menu for each rank', "In Menu Config you choose, per academic rank, how many Research targets faculty must pick, which ones they can pick from, and which Extension targets are mandatory."),
            ('Assign Research directly (optional)', "In Target Assignment you can give a specific faculty member a Research target and track how much of each quota is distributed."),
            ('Wait for faculty to submit', "Faculty with Research or Extension send their drafts to you first."),
            ('Review their RET choices', "In Commitments you check each faculty member's Research and Extension, adjust quantities if needed, and approve or return."),
            ('Monitor evidence', "In Evidence Monitor you follow Research and Extension evidence once the Program Chair has approved it. This page is read-only."),
            ('Lock and evidence your own IPCR', "Lock your own IPCR when the Dean issues it, then report your own accomplishments. Your evidence goes straight to the Dean."),
        ],
        'sections': {
            'nav-overview': {
                'title': 'Overview',
                'purpose': "A snapshot of Research and Extension setup for the current term.",
                'steps': [
                    "Registered Targets is the number of Research and Extension targets available this term.",
                    "Configured Ranks is how many academic rank bands you have already set up rules for.",
                    "If you see No Active Term, the Administrator has not opened a term yet. Wait for them.",
                    "Use the sidebar to open Cascaded Targets, Target Assignment, Menu Config, Commitments and Evidence Monitor, or My IPCR for your personal IPCR.",
                ],
                'tips': [
                    "The Pending Approvals number on this card does not reflect the real count of drafts waiting. Open Commitments to see them.",
                ],
            },
            'nav-phase1': {
                'title': 'Cascaded Targets',
                'purpose': (
                    "A read-only list of the Research and Extension targets the Dean allocated to "
                    "your unit, with the quota for each."
                ),
                'steps': [
                    "Read the Research and Extension sections to see each target and its Quota.",
                    "Use this as your reference when you set up rules in Menu Config.",
                ],
                'tips': [
                    "Nothing on this page can be edited. The quotas are set by the Dean.",
                ],
            },
            'nav-target-assignment': {
                'title': 'Target Assignment',
                'purpose': (
                    "Where you directly assign Research targets to individual Regular Faculty and "
                    "track how much of each RET quota has been distributed."
                ),
                'steps': [
                    "Under Assign Research Targets to Faculty, use Search faculty to find someone.",
                    "Click Assign next to the person. A list of the Research targets on their rank's menu appears.",
                    "Tick the target you want to assign. Set the quantity, the IPCR description and the duration (a number plus a unit). Leave the description blank to use the standard Auto wording.",
                    "Save. The Assign button shows a count of what you have assigned. Reopen it any time to see or change the assignment.",
                    "Scroll to RET Targets with Quotas to see the Distribution Progress, whether each quota is Fully Distributed or Under Distributed, and who holds what.",
                ],
                'tips': [
                    "Every Regular Faculty member can choose Research themselves. Assigning directly is for making sure a target is covered.",
                    "Assignments are limited to what is on that person's rank menu, so configure the rank in Menu Config first.",
                    "An assigned Research target arrives already locked on the faculty member's IPCR, with your description and deadline.",
                ],
            },
            'nav-phase2': {
                'title': 'Menu Config',
                'purpose': (
                    "Where you decide what each academic rank sees. For each rank band you set how "
                    "many Research targets faculty must pick, which Research targets they may pick "
                    "from, and which Extension targets are mandatory."
                ),
                'steps': [
                    "Choose the Academic Rank Band from the dropdown.",
                    "Set Research Required, the number of Research targets each faculty member in that rank must pick.",
                    "Under Research Options, tick every Research target that rank may choose from. For each ticked target enter the quantity, the IPCR description and the duration. A blank description fills in automatically with an Auto badge, and Reset to Auto restores it after you type over it.",
                    "Under Extension Options, set the quantity, description and duration of each Extension target. These are mandatory and locked for everyone in that rank. Auto Divide All sets each quantity to the Dean's quota divided by the total number of Regular Faculty.",
                    "Click Save Menu Rules.",
                    "Check Active Research & Extension Rules below the form. Edit or delete a rank's rule from there.",
                ],
                'tips': [
                    "Saving replaces that rank band's entire Research rule. Any target you leave unticked is removed from it.",
                    "Saving Extension locks it. To make a correction, click Unlock to Edit first, change it, and save again, which locks it once more.",
                    "Check the Auto-generated Extension wording carefully before saving. It goes to every faculty member in that rank.",
                    "If you delete a rule, faculty of that rank no longer see a Research menu until you set one up again.",
                    "Faculty cannot submit their drafts until your rules exist for their rank, so set up every rank in use.",
                ],
            },
            'nav-phase4': {
                'title': 'Commitments',
                'purpose': (
                    "Where you review the Research and Extension choices faculty submit, before "
                    "the Program Chair reviews the rest of their IPCR."
                ),
                'steps': [
                    "The list shows faculty who have submitted, with their rank, specialization and the number of Targets Selected.",
                    "Click Review RET Targets. Submitted Targets shows the Research they chose and the Extension distributed to them. Extension rows are read-only.",
                    "Adjust a Reviewed Qty if needed and explain it in Remarks on this change.",
                    "Unselected Indicators lists Research targets the faculty did not pick. Use it if you need to add coverage.",
                    "Decide: Approve RET Choices sends the draft on to the Program Chair. Return to Faculty sends it back with your remarks. Remarks are optional when approving.",
                    "A faculty member you returned shows as Awaiting Resubmission. When they resubmit, they come back to you.",
                    "Approved RET Choices lists everyone you have approved. Click View RET Targets to look again.",
                ],
                'tips': [
                    "Faculty whose rank has no Research requirement, or who chose none, skip you and go straight to the Program Chair.",
                    "After the Program Chair returns a draft, the faculty member's approved Research stays approved. It does not come back to you.",
                ],
            },
            'nav-evidence-verification': {
                'title': 'Evidence Monitor',
                'purpose': (
                    "A read-only view of Research and Extension evidence for Regular Faculty, shown "
                    "once the Program Chair has approved it."
                ),
                'steps': [
                    "The list shows faculty with Research and Extension targets, how many RET Targets Committed and how many are Met.",
                    "Click View Evidences to see each Research and Extension indicator with its target, accomplished quantity, status and uploaded files.",
                ],
                'tips': [
                    "You cannot approve or return evidence here. The Program Chair approves all Regular Faculty evidence, including Research and Extension.",
                ],
            },
            **_leader_ipcr_sections(
                "Your Instruction share is allocated to you by your Program Chair. If it is missing, ask them."
            ),
        },
        'glossary': [
            ('RET', "Research, Extension and Training. The three areas your unit oversees."),
            ('Rank band', "A group of academic ranks that share the same Research and Extension rules."),
            ('Research Required', "How many Research targets a faculty member in a rank must pick."),
            ('Research menu', "The Research targets a rank may choose from. Faculty pick from it."),
            ('Extension (mandatory)', "Extension targets that are locked onto every faculty member in a rank. They are not chosen."),
            ('Quota', "The number the Dean assigned to your unit for a target."),
            ('Program Chair', "Reviews the rest of a faculty draft after you, and verifies all Regular Faculty evidence."),
            ('Dean', "Prepares your personal IPCR and gives the final approval of evidence."),
            ('Returned', "Sent back with remarks so the faculty member can fix and resubmit."),
            ('Q, E, T', "Ratings computed by the system for each target. They roll up into a Final Weighted Rating."),
        ],
        'faq': [
            ('Faculty say they have no Research menu.', "No rule exists for their rank yet, or it was deleted. Set it up in Menu Config."),
            ('I saved an Extension target with the wrong wording.', "Click Unlock to Edit in Menu Config, correct it and save again."),
            ('A faculty draft is not in Commitments.', "They may not have chosen Research, or their rank has none required, so it went straight to the Program Chair. Otherwise they may not have submitted yet."),
            ('Why can I not approve Research evidence?', "The Program Chair approves all Regular Faculty evidence now. Evidence Monitor is for following progress only."),
            ('I cannot assign a Research target to someone.', "Assignments are limited to the target on their rank's menu. Add it to that rank in Menu Config first."),
            ('I cannot lock my own IPCR.', "Your Instruction share may not be allocated to you yet. Ask your Program Chair, then come back."),
        ],
    },

    'DEAN': {
        'label': 'College Dean',
        'home_endpoint': 'dean.dean_dashboard',
        'intro': (
            "As Dean you start the cascade by setting each department's quotas, you prepare the "
            "IPCRs of the Program Chairs, the RET Chair and yourself, you review drafts from "
            "Designated Faculty, and you give the final approval on everyone's evidence. This "
            "manual walks you through each step."
        ),
        'journey': [
            ('Cascade the college quotas', "In Quota Cascading you set each master indicator's quota per department, for RET / Extension and for College-Wide. This is a one-time action per term."),
            ('Assign to designated faculty and chairs', "In Target Assignment you draft and issue the IPCRs of the Program Chairs, RET Chair and yourself, and assign College-Wide targets to Designated Faculty."),
            ('Review Designated Faculty drafts', "In IPCR Draft Approval you check each Designated Faculty draft, adjust quantities, and approve or return."),
            ('Track progress', "Overview and Department Accomplishment show how far each department has come."),
            ('Review your unreviewed evidence', "In Evidence Verification you check the files of Designated Faculty, chairs and your own, since nobody else reviews them."),
            ('Give final approval', "In Final Verification you review each complete IPCR and approve it or return it to the faculty member."),
            ('Lock and evidence your own IPCR', "Lock your own IPCR once it is issued, then report your own accomplishments."),
        ],
        'sections': {
            'nav-overview': {
                'title': 'Overview',
                'purpose': "A college-wide snapshot of progress for the current term.",
                'steps': [
                    "Target Completion is the share of committed target items marked Approved across all programs. It counts targets, not people.",
                    "Awaiting Final Approval is how many final IPCRs are waiting in Final Verification. Click it to go there.",
                    "Not Yet Started is how many Regular Faculty have no draft targets this term.",
                    "Term Completion Tracker breaks Regular Faculty down by department into Total, In Progress, Awaiting Your Approval and Completed.",
                ],
                'tips': [
                    "The tracker's Awaiting Your Approval covers Regular Faculty only, while the Awaiting Final Approval card above it also includes Designated Faculty, chairs and you. The two numbers will not always match.",
                ],
            },
            'nav-phase1': {
                'title': 'Quota Cascading',
                'purpose': (
                    "Where you set the institutional targets for the term. You give each master "
                    "indicator a quota per department, for RET / Extension and for College-Wide. "
                    "Everything downstream is built from this."
                ),
                'steps': [
                    "The table lists each master indicator with one column per department, plus RET / Extension and College-Wide.",
                    "Enter a quota for every indicator in every column that applies.",
                    "Click Cascade Institutional Targets. If any indicator is left unassigned, a warning names it and blocks you. Fill it in and try again.",
                    "The confirmation shows how many targets you are about to cascade. Read it, then click Confirm & Cascade.",
                    "The page then shows Cascaded & Locked. Use Go to Target Assignment to continue.",
                ],
                'tips': [
                    "Cascading is a one-time action for the term and permanently locks the quotas. Check the numbers carefully first.",
                    "Program Chairs and the RET Chair can start their own work only after you cascade.",
                    "A deactivated department does not appear as a column.",
                ],
            },
            'nav-draft-ipcr': {
                'title': 'IPCR Draft Approval',
                'purpose': (
                    "Where you review the draft IPCRs that Designated Faculty submit, and approve "
                    "them or send them back."
                ),
                'steps': [
                    "Pending Draft Submissions lists drafts awaiting review or returned for revision, with each person's rank, designation and number of targets.",
                    "Click Review to open a draft. Core Functions and Strategic Priorities & Support Functions each show the original quantity, a Reviewed Qty you may change, the deadline, and a box for your remarks on that target.",
                    "Unselected Indicators lists targets the person did not pick. You can assign quantities to them if needed.",
                    "Decide: Approve IPCR lets the person lock it. Reject & Return to Faculty sends it back with your remarks.",
                    "Approved IPCR Drafts lists what you have approved. Click View to look again.",
                ],
                'tips': [
                    "The faculty member sees your remarks on the draft when it is returned and can resubmit.",
                    "Program Chairs, the RET Chair and you do not go through this page. Your IPCRs are drafted in Target Assignment.",
                ],
            },
            'nav-target-assign': {
                'title': 'Target Assignment',
                'purpose': (
                    "Where you prepare the IPCRs of Program Chairs, the RET Chair and yourself, "
                    "and assign College-Wide targets to Designated Faculty."
                ),
                'steps': [
                    "College-Wide Targets with Quotas at the top shows each College-Wide indicator and its quota.",
                    "Use Search faculty or chair to find a person in the table. The Draft IPCR Status column shows Not Started, Drafted or Issued / Approved.",
                    "Click Draft IPCR to open the Draft IPCR Studio for that person.",
                    "Core Functions shows their teaching load and instruction share as read-only previews. Instruction is distributed by the Program Chair, not here.",
                    "Strategic Priorities & Support Functions shows the person's departmental oversight targets. Their quantity is fixed at the whole cascaded quota and only the deadline is editable. Tick any College-Wide targets to assign as well, with a quantity, description and duration.",
                    "Click Save & Issue Draft IPCR for a Program Chair, the RET Chair or yourself. For plain Designated Faculty the button is Save Assignments.",
                ],
                'tips': [
                    "A blank description fills in automatically with the standard wording and an Auto badge.",
                    "A locked and committed IPCR cannot be re-issued. The Studio tells you so.",
                    "An issued chair IPCR arrives pre-approved, so the chair only has to check and lock it.",
                ],
            },
            'nav-department-accomplishment': {
                'title': 'Department Accomplishment',
                'purpose': (
                    "Compares the quota cascaded to each department with the accomplishment "
                    "already approved by its Program Chair."
                ),
                'steps': [
                    "Choose a department tab.",
                    "For each Departmental Oversight Target, read the Quota, the Verified Accomplished figure and the Progress bar.",
                ],
                'tips': [
                    "Verified means already approved by the Program Chair, not just reported. It is a monitoring view and does not affect scoring.",
                    "A department with nothing cascaded yet shows an empty message.",
                ],
            },
            'nav-evidence-verification': {
                'title': 'Evidence Verification',
                'purpose': (
                    "Where you review the evidence files of Designated Faculty, Program Chairs, "
                    "the RET Chair and yourself. Nobody else reviews them, so you do it here "
                    "before final approval."
                ),
                'steps': [
                    "Pending Evidence Verification lists the people whose evidence is waiting, with their designation and the state of their evidence.",
                    "Click Review Evidence to open the files.",
                    "For each file, open it and choose to approve it or return it. Add a reason when you return one so the person knows what to fix.",
                    "When every file has a decision the person shows as Fully Reviewed and moves on to Final Verification.",
                ],
                'tips': [
                    "Regular Faculty evidence does not appear here. Their Program Chair reviews it and sends the package to Final Verification.",
                    "Your own evidence appears in this list too.",
                ],
            },
            'nav-final-verification': {
                'title': 'Final Verification',
                'purpose': (
                    "Your last review of each person's complete IPCR, after the evidence is "
                    "verified. Approving it makes the IPCR final."
                ),
                'steps': [
                    "Pending Final Verification lists packages awaiting you. Regular Faculty appear after their Program Chair submits them. Designated Faculty and chairs appear after you finish reviewing their files.",
                    "Click Review IPCR. The official IPCR form opens in the window with the commitments, accomplishments, Q, E, T scores, summary ratings and signatories.",
                    "Click Approve IPCR to finalize it, or Return to Faculty to send it back with a reason.",
                    "The two Approved tables list finalized IPCRs, one for Designated Faculty and chairs, and one for Regular Faculty. Click View IPCR to open any of them again.",
                ],
                'tips': [
                    "After approval the person can print their finalized IPCR.",
                    "The red number on Final Verification in the sidebar is how many packages are waiting.",
                ],
            },
            **_leader_ipcr_sections(
                "Your Instruction share is allocated to you by your department's Program Chair. If it is missing, ask them.",
                self_issued=True,
            ),
        },
        'glossary': [
            ('Quota', "The number you assign to a department, RET or College-Wide for a master indicator."),
            ('Cascade', "Sending the quotas down to the Program Chairs and the RET Chair. A one-time, locking action for the term."),
            ('College-Wide target', "A target you assign directly to Designated Faculty or a chair, not to a department."),
            ('Draft IPCR Studio', "The window in Target Assignment where you prepare and issue a chair's or Designated Faculty's IPCR."),
            ('Departmental Oversight', "A chair's own target for their whole department's cascaded quota. The quantity is fixed and only the deadline is editable."),
            ('Issued', "A draft IPCR you have finished preparing and sent to the person, pre-approved."),
            ('Verified', "Approved by the reviewer, not just reported."),
            ('Final Verification', "Your last review, where an IPCR becomes final."),
            ('Returned', "Sent back with remarks so the person can fix and resubmit."),
            ('Q, E, T', "Ratings computed by the system for each target. They roll up into a Final Weighted Rating."),
        ],
        'faq': [
            ('I cannot cascade.', "At least one indicator has no quota. The warning names it. Fill it in and try again."),
            ('I cascaded with a wrong number.', "Cascading is one-time and locks the quotas for the term. Contact the system Administrator."),
            ('A Designated Faculty draft is not in IPCR Draft Approval.', "They have not submitted yet. Chairs and the RET Chair never appear there because you issue their IPCRs from Target Assignment."),
            ('A Regular Faculty member is not in Final Verification.', "Their Program Chair has to approve their evidence and click Submit to Dean first."),
            ('Why does the Overview show two different pending numbers?', "The tracker counts Regular Faculty only, while the KPI card also counts Designated Faculty, chairs and you."),
            ('I cannot lock my own IPCR.', "Issue it to yourself first from Target Assignment. Your Instruction share must also be allocated by your Program Chair."),
        ],
    },

    'ADMIN': {
        'label': 'System Administrator',
        'home_endpoint': 'admin.admin_dashboard',
        'intro': (
            "As Administrator you prepare everything the rest of the college depends on. You open "
            "the term, set up departments, teaching load, criteria, weights and master indicators, "
            "keep the faculty roster correct, and look after accounts. Nobody else can start "
            "their part until you finish yours, and a few of your settings cannot be changed "
            "afterwards. This manual walks you through each step."
        ),
        'journey': [
            ('Open the term', "In Term Configuration you open the academic term. Only one term can be active at a time, and opening a new one deactivates the others."),
            ('Set up the institution', "In Institution Setup you confirm the departments, the mandatory teaching load, and the header and signatories that print on the IPCR."),
            ('Set up the criteria', "In Criteria you confirm the target types, how they are grouped into IPCR categories for each designation, and the weight each category carries."),
            ('Define the master indicators', "In Master Indicators you list every standard target, or import last term's list."),
            ('Check the roster', "In Faculty Configuration you make sure every person's specialization, rank and designation is right. Targets and login roles depend on it."),
            ('Approve account claims', "Employees claim their pre-created profile when they register. You approve them in Account Claims so they can sign in."),
            ('Hand over to the Dean', "Once the setup is complete, the Dean cascades the quotas."),
            ('Maintain during the term', "Reset passwords, lock accounts, review the audit log and download database backups."),
        ],
        'sections': {
            'nav-overview': {
                'title': 'Overview',
                'purpose': "A snapshot of the system's setup and how many people have taken up their accounts.",
                'steps': [
                    "Roster Adoption Rate shows how many pre-registered profiles have been claimed by their owners.",
                    "Active Academic Term shows the term that is currently open, or No Active Term.",
                    "After you open a term, a reminder appears asking you to recheck Faculty Configuration. Click Review Now to go there, or Mark as Reviewed once you have done it.",
                ],
                'tips': [
                    "Recheck each person's Designation before faculty start submitting. Changing it changes their login role at their next sign-in.",
                ],
            },
            'nav-term': {
                'title': 'Term Configuration',
                'purpose': (
                    "Where you open an academic term. Everything in the system, including quotas, "
                    "weights and IPCRs, belongs to a term."
                ),
                'steps': [
                    "Enter the Academic Year in the format YYYY - YYYY with consecutive years, for example 2025 - 2026.",
                    "Choose the Semester: 1st Semester, 2nd Semester or Mid Year.",
                    "Set the Rating Period From and To. These dates print in the header of the IPCR as the period being rated.",
                    "Click Open Term & Deactivate Others.",
                    "Term History below lists every term with its Semester and whether it is Active or Locked.",
                ],
                'tips': [
                    "Only one term can be active. Opening a new one deactivates every other term, for everybody using the system.",
                    "A term for the same Academic Year and Semester cannot be opened twice, and there is no undo. Check the details before you click.",
                    "Before opening a term, make sure nobody is in the middle of work in the current one.",
                    "After opening a term, most of the setup below needs to be done for it, or copied from the previous term.",
                ],
            },
            'nav-roster': {
                'title': 'Faculty Configuration',
                'purpose': (
                    "The roster of every employee who uses the system. You create their profile "
                    "here first, and they claim it later when they register."
                ),
                'steps': [
                    "Click Add New Faculty and fill in the Employee ID Number, name, College, Assigned Program, Specialization, Academic Rank, Employment Status and Designation.",
                    "Or click Upload CSV Roster to add many people at once.",
                    "Use the table to check each person's Program, Specialization, Rank, Designation and Status.",
                    "To change someone's details, edit their row. Use Deactivate or Activate to remove them from, or restore them to, allocation and assignment lists.",
                ],
                'tips': [
                    "Specialization is the department. It decides which Program Chair distributes to the person and which Dean quota applies.",
                    "Designation decides whether someone has their own IPCR and how it is scored. Changing it also changes their login role at their next sign-in.",
                    "Registration cannot create a profile from scratch. It can only claim one that is already on the roster.",
                    "Read the results after a CSV upload. A malformed row is reported rather than silently skipped.",
                ],
            },
            'nav-institution': {
                'title': 'Institution Setup',
                'purpose': (
                    "Three settings for the whole institution: the departments, the mandatory "
                    "teaching load, and the text and signatures that print on every IPCR."
                ),
                'steps': [
                    "Departments / Programs: use Add Department to create one with a name, short code and order. Use the arrows to reorder, and Deactivate to hide one.",
                    "Teaching Load: for each designation type, set the hours, duration and unit. Choose Same for all ranks, or per academic rank band, then Save. The fields lock after saving. Use Edit to change them.",
                    "Printed IPCR: check the College Full Name.",
                    "For each signature block, set who it is filled from: a named person, their Program Chair, or the Dean. A derived choice disables the Name field.",
                    "Enter the Position Label and, for a named person, the Name. Then click Save Signatories.",
                ],
                'tips': [
                    "Departments drive the Dean's cascade columns and the roster's specialization list. Renaming one also updates the faculty and quotas that use it.",
                    "A deactivated department disappears from the Dean's cascade.",
                    "Teaching load is added to every IPCR automatically. Its duration drives the Timeliness rating.",
                    "A named-person signature block cannot be saved with an empty name.",
                ],
            },
            'nav-criteria': {
                'title': 'Criteria',
                'purpose': (
                    "Defines how targets are classified and scored: the target types, the IPCR "
                    "categories they are grouped into, and the weight each category carries."
                ),
                'steps': [
                    "Performance Criteria lists the target types. Each has a Slug, a Review Lane (Program Chair, or RET Chair for Research and Extension), a Core flag and an order.",
                    "Category Management: for Regular Faculty and for Designated Faculty separately, choose which target types belong to each IPCR category. Instruction sits in a different category for each designation.",
                    "Weight Allocation by Rank: enter the percentage each category carries, for all ranks or per academic rank band, separately for Regular and Designated Faculty.",
                    "Each row must total exactly 100%, otherwise saving is refused. Click Save when it is right.",
                    "If the term is new, use Copy from Previous Term to bring the earlier weights across.",
                ],
                'tips': [
                    "The system relies on six built-in slugs: instruction, research, extension, support, administrative and custom. If you add or rebuild a criterion, set its Slug to one of these by hand where it applies. A generated slug breaks the review routing without any error message.",
                    "Editing a criterion changes its name but never its slug.",
                    "The usual weights are 50 / 40 / 10 for Regular Faculty and 75 / 25 for Designated Faculty.",
                    "Weights are per term. Set them again, or copy them, after you open a new term.",
                ],
            },
            'nav-indicators': {
                'title': 'Master Indicators',
                'purpose': (
                    "The standard list of targets for the term, grouped by IPCR category. The "
                    "Dean, chairs and faculty all build their targets from this list."
                ),
                'steps': [
                    "If the term has no indicators yet, click Import from Previous Term to start from last term's list.",
                    "Under a category, click Add Target. Choose the Target Type, then write the Success Indicator (target and measure).",
                    "Choose the Efficiency Type: Quantity-Based (E follows the quantity achieved), Adjectival (the target uses a quality adjective such as accurately or completely, and E is always 5) or Client Satisfaction (E is the client's reported rating).",
                    "To make the wording adapt to different quantities and deadlines, click the number in the description to tag it as Qty, and click the duration to tag it as Dur. Use Undo last tag to reverse it.",
                    "Edit an indicator's description or efficiency type from its row. Delete removes an indicator that nothing uses yet.",
                ],
                'tips': [
                    "Tagging turns a sentence like 'Submit 51 reports within 10 days' into one that reads correctly for any quantity and deadline assigned later. Without tags the system prepends the quantity and appends the duration, which only reads well for a bare activity name.",
                    "Client Satisfaction indicators ask the faculty member for a satisfaction rating when they report evidence.",
                    "Administrative Functions indicators are needed for chairs' and the Dean's oversight targets.",
                    "An indicator that already has targets against it cannot be deleted.",
                ],
            },
            'nav-claims': {
                'title': 'Account Claims',
                'purpose': (
                    "Approve or deny employees who registered to claim their pre-created profile."
                ),
                'steps': [
                    "Pending Claims lists each request with the Employee ID, name, designation, corporate email and system role.",
                    "Check that the person matches the profile on your roster.",
                    "Click Approve to let them sign in.",
                    "Deny removes the request. The person can claim again.",
                ],
                'tips': [
                    "A claim only works after you approve it.",
                    "A red number beside Account Claims in the sidebar is how many are waiting.",
                    "The first Administrator account cannot be created here. It comes from the bootstrap script.",
                ],
            },
            'nav-security': {
                'title': 'System Security',
                'purpose': (
                    "Emergency access controls for user accounts, and a read-only audit trail of "
                    "what has been done."
                ),
                'steps': [
                    "Search or filter the account list by name, role or status.",
                    "Click Issue Temp Password to give someone a new temporary password, for example when they are locked out.",
                    "Click Lock Account to stop someone from signing in, or Unlock Account to let them back. A locked person is refused immediately, even if they are already signed in.",
                    "Activity Audit Log shows the last 50 system actions, newest first, with the timestamp, who did it, what happened and their IP address.",
                ],
                'tips': [
                    "Every action here is permanently recorded in the audit log.",
                    "The audit log is read-only.",
                    "For a full database backup, use Backup Database in the sidebar. It downloads a .sql file.",
                ],
            },
        },
        'glossary': [
            ('Term', "One academic period, such as 2025 - 2026, 1st Semester. Only one term is active at a time."),
            ('Master indicator', "A standard target defined by you, from which everyone else builds their IPCR."),
            ('Criterion / target type', "A kind of target, such as Instruction, Research, Extension or Support."),
            ('Slug', "A short fixed code for a criterion. The system matches on the six built-in ones."),
            ('Review lane', "Which chair reviews targets of a criterion: the Program Chair or the RET Chair."),
            ('IPCR category', "A scored group on the IPCR, such as Core Functions. Regular and Designated Faculty group target types differently."),
            ('Weight', "The percentage a category contributes to the Final Weighted Rating. Each set must total 100%."),
            ('Designation', "A person's job title. It decides whether they have their own IPCR and how it is scored."),
            ('Specialization', "The department a person belongs to."),
            ('Claim', "A registration request from an employee to take over a profile you created."),
        ],
        'faq': [
            ('Someone cannot register.', "Their profile must already exist on the roster. Create it in Faculty Configuration first, then approve their claim."),
            ('A person cannot sign in after registering.', "Their claim needs your approval in Account Claims."),
            ('The weights will not save.', "Each row must add up to exactly 100%. The warning shows which row is off."),
            ('The Dean does not see a department.', "It may be deactivated in Institution Setup."),
            ('Faculty see the wrong targets or weights.', "Check their Designation and Specialization in Faculty Configuration."),
            ('I opened the wrong term.', "A term cannot be reopened or duplicated once it exists for that Academic Year and Semester, and there is no undo on this screen. Check the details before you click, and ask whoever manages the database if it is already done."),
            ('Someone forgot their password.', "Use Issue Temp Password in System Security."),
        ],
    },
}


def help_for_role(role):
    """The help entry for a login role, or None when that role has no help written yet."""
    return HELP.get((role or '').upper())
