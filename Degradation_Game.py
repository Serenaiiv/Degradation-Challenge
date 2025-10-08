import streamlit as st
import pandas as pd
import numpy as np
import time
import uuid
from datetime import datetime

# ----------------------------
# APP-WIDE CONSTANTS (edit me)
# ----------------------------
APP_TITLE = "Degradation Challenge Game"
TARGET_HOURS = 3.0  # objective: complete degradation at ~3 hours
MAX_ENTRIES_PER_RUN = 5  # allow up to 5 per "batch" (paper-style)
WAVELENGTHS = np.arange(300, 801, 2)  # 300–800 nm UV-Vis window

SOLVENTS = ["2MeTHF", "Toluene", "Chloroform"]
POLYMER_CONCENTRATION = [0.01, 0.05, 0.10]  # mg/mL (display only for now)
ACIDS = ["HCl", "TFA"]
ACID_CONCENTRATION = ["50x", "100x", "300x", "600x", "900x"]  # "x" relative to imine

# ----------------------------
# UTILS: SESSION & TIMER
# ----------------------------
def init_state():
    """Initialize session_state keys if absent."""
    ss = st.session_state
    ss.setdefault("page", "Welcome")
    ss.setdefault("session_id", str(uuid.uuid4()))
    ss.setdefault("survey", {})  # dict of basic demographics
    ss.setdefault("consented", False)

    # entries added but not yet "run"
    ss.setdefault("pending_entries", [])
    # results from runs (list of dict rows)
    ss.setdefault("results", [])

    # timer
    ss.setdefault("timer_started_at", None)   # epoch seconds
    ss.setdefault("timer_stopped_at", None)   # epoch seconds
    ss.setdefault("timer_running", False)

    # bookkeeping for simple analytics
    ss.setdefault("first_opened_builder_at", None)
    ss.setdefault("ended", False)

def now_epoch():
    return time.time()

def start_timer_if_needed():
    """Kick off the timer the first time Experiment Builder is opened."""
    ss = st.session_state
    if not ss.timer_running:
        ss.timer_started_at = now_epoch()
        ss.timer_running = True

def stop_timer():
    ss = st.session_state
    if ss.timer_running:
        ss.timer_stopped_at = now_epoch()
        ss.timer_running = False

def elapsed_seconds():
    ss = st.session_state
    start = ss.get("timer_started_at")
    stop = ss.get("timer_stopped_at")
    running = ss.get("timer_running", False)

    if start is None:
        return 0.0
    if running:
        return max(0.0, now_epoch() - float(start))
    if stop is not None:
        return max(0.0, float(stop) - float(start))
    return 0.0

def pretty_hms(seconds: float) -> str:
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"

def reset_for_new_attempt():
    """Clear results and pending entries, reset timer and flags, and mint a new session."""
    ss = st.session_state
    ss.session_id = str(uuid.uuid4())
    ss.pending_entries = []
    ss.results = []
    ss.timer_started_at = None
    ss.timer_stopped_at = None
    ss.timer_running = False
    ss.first_opened_builder_at = None
    ss.ended = False
    # keep survey/consent so the user doesn't have to refill; uncomment to clear:
    # ss.survey = {}
    # ss.consented = False
    ss.page = "Welcome"  # go back to Welcome for a fresh run

# ----------------------------
# SIMPLE SIMULATOR
# ----------------------------
def base_degradation_time(solvent: str, acid: str, mult: str) -> float:
    """A small handcrafted landscape with local traps."""
    # start with a baseline
    t = 6.0  # hours

    # solvent effects
    if solvent == "2MeTHF":
        t -= 1.2
    elif solvent == "Chloroform":
        t -= 0.6
    elif solvent == "Toluene":
        t += 0.4

    # acid identity
    if acid == "HCl":
        t -= 0.8
    elif acid == "TFA":
        t -= 0.3

    # acid strength multiplier (nonlinear, best around mid-high)
    mult_val = int(mult.replace("x", ""))
    if mult_val <= 50:
        t += 1.0
    elif mult_val == 100:
        t -= 0.2
    elif mult_val == 300:
        t -= 0.9
    elif mult_val == 600:
        t -= 0.6
    elif mult_val == 900:
        t -= 0.1

    # small randomness (experimental noise)
    noise = np.random.normal(0, 0.15)
    t = max(0.4, t + noise)
    return float(np.round(t, 2))

# score: closeness to 3h (lower is better)
def closeness_score(hours: float) -> float:
    return float(np.round(abs(hours - TARGET_HOURS), 3))

# ----------------------------
# LAYOUT: SIDEBAR NAV + TIMER
# ----------------------------
def sidebar():
    # live time readout (ticks because main() re-runs while timer_running=True)
    st.sidebar.markdown("### ⏱️ " + pretty_hms(elapsed_seconds()))

    pages = [
        "Welcome",
        "Survey",
        "Instructions",
        "Experiment Builder",
        "Experiment Results",
        "Progress Tracker",
        "End Experiment",
    ]
    # Gate the gameplay pages until consent
    requires_consent = {"Instructions", "Experiment Builder", "Experiment Results", "Progress Tracker", "End Experiment"}
    consented = st.session_state.get("consented", False)

    for p in pages:
        disabled = (p in requires_consent) and (not consented)
        if st.sidebar.button(p, use_container_width=True, disabled=disabled):
            st.session_state.page = p
            # IMPORTANT: do NOT start the timer here; only in page_builder()
            # This prevents pre-consent timer starts.

    st.sidebar.markdown("---")
    st.sidebar.caption("⏱️ Timer starts when you first open *Experiment Builder* (after consenting) and stops on *End Experiment*.")



# ----------------------------
# PAGES
# ----------------------------
def page_welcome():
    st.markdown("## Welcome")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("robot_vs_human_welcome.png", width=700)
    st.write(
        """
**Welcome to the Degradation Challenge Game!**  
This is a simulation game to simulate setting up and running experiments to study pi-conjugated polymer degradation. 
This game is part of a research project in Team Tran on comparing decision-making of human scientist vs self-driving laboratories (SDLs) in polymer chemistry.  

- Estimated time to complete the game: >30 minutes  
- We will collect your background info and game data for research (see Terms & Consent in the **Survey**).
- You may remain anonymous if you prefer but we do ask for your educational background to better evaluate human scientist performance.

Please find the instructions of the game in the **Instructions** page after completing the **Survey** and giving consent.

If you have questions, contact Serena: serenazuyun.qiu@mail.utoronto.ca

**When you’re ready, continue to the Survey.**
        """
    )
    if st.button("Go to Survey", use_container_width=True):
        st.session_state.page = "Survey"
        st.rerun()

def page_survey():
    st.markdown("## Survey")
    st.write("Please complete the survey. Consent is required to proceed.")

    # External link to your Terms/Consent page
    st.write(
        "📄 **Read the Terms & Consent**: "
        "[Terms](https://utoronto-my.sharepoint.com/:w:/g/personal/serenazuyun_qiu_mail_utoronto_ca/EVrw_cgiBVdGg7T7Jr5mqhABApoJ5u5QJ_3s_QIMAHcKYQ?e=Y6YXin)"
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        name = st.text_input("Name")
        email = st.text_input("Email")
        inst = st.text_input("Institution")
        dept = st.text_input("Department/Discipline")
    with col2:
        role = st.selectbox("Role", ["Undergraduate", "Graduate Student", "Postdoc", "Faculty/Staff", "Other"])
        experience = st.selectbox(
            "Experience in polymer chemistry", ["None", "< 1 year", "1–3 years", "3–5 years", "5+ years"]
        )

    consent = st.checkbox("I have read the Terms & Consent and I agree to participate.")

    if st.button("Save and Continue"):
        st.session_state.survey = dict(
            name=name, email=email, institution=inst, department=dept,
            role=role, experience=experience
        )
        st.session_state.consented = bool(consent)
        if not consent:
            st.warning("Consent is required to continue.")
        else:
            st.success("Consent recorded. Thank you!")
            st.session_state.page = "Instructions"
            st.rerun()

def page_instructions():
    st.header("Introduction & Game Rules")
    st.subheader("Purpose")
    st.write(
        "Your goal is to choose experimental conditions that produce **complete degradation** "
        f"as close as possible to **{TARGET_HOURS} hours**."
    )

    st.subheader("Rules")
    st.write(
        """
- Build experiments on the **Experiment Builder** page.  
- You can add multiple entries; run them to see results.  
- Each run returns spectra for your entries.  
- No AI tools during gameplay. Take notes if you like.  
- When done, go to **End Experiment** to stop the timer and download your data.
        """
    )

    if st.button("I understand. Let's start!"):
        if not st.session_state.consented:
            st.info("Please complete the Survey and give consent before playing.")
        else:
            st.session_state.page = "Experiment Builder"
            st.rerun()

def page_builder():
    st.header("Experiment Builder")
    if not st.session_state.consented:
        st.warning("You must consent on the Survey page before playing.")
        return

    # Start timer on first entry to this page (only after consent)
    start_timer_if_needed()

    # Selection widgets
    st.write("**Select Conditions and Add as Entries**")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        solvent = st.selectbox("Solvent", SOLVENTS, index=0)
    with c2:
        conc = st.selectbox("Polymer Concentration (mg/mL)", POLYMER_CONCENTRATION, index=0)
    with c3:
        acid = st.selectbox("Acid Type", ACIDS, index=0)
    with c4:
        acid_conc = st.selectbox("Acid Concentration*", ACID_CONCENTRATION, index=2)
    with c5:
        spectrum_hour = st.selectbox("Spectrum Hour to View", [0.5, 1.0, 2.0, 3.0, 4.0, 5.0], index=3)

    st.caption("*Acid molar excess relative to imine groups in polymer.")

    # Buttons aligned left and far-right
    col_left, col_spacer, col_right = st.columns([1, 3, 1])
    with col_left:
        if st.button("Add Entry"):
            st.session_state.pending_entries.append(dict(
                entry_id=f"{st.session_state.survey.get('name','anon')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                solvent=solvent,
                polymer_conc=conc,
                acid=acid,
                acid_conc=acid_conc,
                spectrum_hour=spectrum_hour,
                added_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            ))
    with col_right:
        if st.button("🧹 Clear Pending"):
            st.session_state.pending_entries = []

    # Show pending entries
    st.write("**Pending Entries (not yet run):**")
    if st.session_state.pending_entries:
        df = pd.DataFrame(st.session_state.pending_entries)
        st.dataframe(df, use_container_width=True)
    else:
        st.caption("No pending entries yet.")

    # Run limit message (only on this page)
    st.subheader(f"You can run up to {MAX_ENTRIES_PER_RUN} entries at a time.")

    # Run button
    can_run = 0 < len(st.session_state.pending_entries) <= MAX_ENTRIES_PER_RUN
    if st.button("▶️ Run Experiments", disabled=not can_run):
        rows = []
        for e in st.session_state.pending_entries:
            hours = base_degradation_time(e["solvent"], e["acid"], e["acid_conc"])
            rows.append(dict(
                session_id=st.session_state.session_id,
                entry_id=e["entry_id"],
                solvent=e["solvent"],
                polymer_conc=e["polymer_conc"],
                acid=e["acid"],
                acid_conc=e["acid_conc"],
                spectrum_hour=e["spectrum_hour"],
                degradation_hours=hours,
                closeness=closeness_score(hours),
                run_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            ))
        st.session_state.results.extend(rows)
        st.session_state.pending_entries = []
        st.success("Run complete! Check **Experiment Results** or **Progress Tracker**.")


def page_results():
    st.header("Experiment Results")
    if not st.session_state.results:
        st.info("No results yet. Add entries and click **Run** on the Experiment Builder page.")
        return

    # Table of results
    df = pd.DataFrame(st.session_state.results)
    show_cols = ["entry_id", "solvent", "polymer_conc", "acid", "acid_conc", "spectrum_hour",
                 "degradation_hours", "closeness", "run_at"]
    st.dataframe(df[show_cols].sort_values("run_at"), use_container_width=True)

    # Display corresponding photo for each entry's selected spectrum hour
    st.markdown("---")
    st.subheader("View Spectrum Photo for a Result")
    entry_ids = [r["entry_id"] for r in st.session_state.results]
    sel = st.selectbox("Choose an entry", entry_ids)
    rec = next(r for r in st.session_state.results if r["entry_id"] == sel)
    spectrum_hour = rec["spectrum_hour"]
    # New photo filename format: solvent_polymerconc_acid_acidconc_spectrumhour.png
    # e.g. toluene_0.5_HCl_100x_3.0.png
    photo_filename = f"{rec['solvent']}_{rec['polymer_conc']}_{rec['acid']}_{rec['acid_conc']}_{spectrum_hour}.png"
    try:
        st.image(photo_filename, caption=f"Spectrum at {spectrum_hour} hours", use_column_width=True)
    except Exception:
        st.warning(f"Photo for {spectrum_hour} hours not found: {photo_filename}")

def page_progress():
    st.header("Progress Tracker")
    if not st.session_state.results:
        st.info("No results yet. Run some experiments first.")
        return

    df = pd.DataFrame(st.session_state.results)
    total_entries = len(df)
    # Each experiment is a batch/run, so count unique run_at timestamps
    total_experiments = df['run_at'].nunique() if not df.empty else 0

    st.metric(label="Total Entries", value=total_entries)
    st.metric(label="Total Experiments", value=total_experiments)

    st.metric(label="Target (hours)", value=f"{TARGET_HOURS:.1f}")


    # Dot plot: experiment number vs. degradation time
    st.write("### Experiment Number vs. Degradation Time (Dot Plot)")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.scatter(np.arange(1, len(df) + 1), df["degradation_hours"].astype(float), color='blue')
    ax.axhline(TARGET_HOURS, linestyle="--", color='red', label='Target')
    ax.set_xlabel("Experiment Number")
    ax.set_ylabel("Degradation time (h)")
    ax.set_title("Degradation Time per Entry")
    ax.legend()
    st.pyplot(fig)

def page_end():
    st.header("End Experiment")
    if not st.session_state.ended:
        stop_timer()
        st.session_state.ended = True

    total_time = pretty_hms(elapsed_seconds())
    st.success(f"Experiment ended. Total time spent: {total_time}")

    # Assemble all data for export (survey + results)
    results = pd.DataFrame(st.session_state.results)
    if not results.empty:
        # Add a column for the date the record is reported
        report_date = datetime.now().strftime('%Y-%m-%d')
        results.insert(0, 'report_date', report_date)
        results = results.assign(
            participant_name=st.session_state.survey.get("name", ""),
            participant_email=st.session_state.survey.get("email", ""),
            session_id=st.session_id,
            total_time_hms=total_time
        )

        csv = results.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download CSV (all results)",
            data=csv,
            file_name=f"game_results_{st.session_state.session_id}.csv",
            mime="text/csv",
            use_container_width=True
        )

        # --- Microsoft Excel Export (append to one file for all players) ---
        try:
            import openpyxl
            excel_filename = "game_results_all_players.xlsx"
            from pathlib import Path
            if Path(excel_filename).exists():
                # Load existing file and append
                existing = pd.read_excel(excel_filename)
                combined = pd.concat([existing, results], ignore_index=True)
                combined.to_excel(excel_filename, index=False)
            else:
                results.to_excel(excel_filename, index=False)
            st.success(f"Results appended to Excel file: {excel_filename}")
        except Exception as e:
            st.warning(f"Excel export failed: {e}")
    else:
        st.info("No experiment results to export.")

    st.markdown("---")
    if st.button("New Attempt", use_container_width=True):
        reset_for_new_attempt()
        st.rerun()

    st.caption("You can start a new attempt above (redirects to *Welcome*) or close the app.")

# ----------------------------
# MAIN
# ----------------------------
def main():
    # Keep this at the top
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_state()

    # Render UI
    sidebar()
    st.title(APP_TITLE)

    # Router
    page = st.session_state.page
    if page == "Welcome":
        page_welcome()
    elif page == "Survey":
        page_survey()
    elif page == "Instructions":
        page_instructions()
    elif page == "Experiment Builder":
        page_builder()
    elif page == "Experiment Results":
        page_results()
    elif page == "Progress Tracker":
        page_progress()
    elif page == "End Experiment":
        page_end()
    else:
        page_welcome()

 
    # After rendering everything, schedule a tick only if consented AND timer is running
    if st.session_state.get("timer_running", False) and not st.session_state.get("ended", False):
        time.sleep(1)
        st.rerun()



if __name__ == "__main__":
    main()
