# app.py
# Streamlit MVP of a human "reaction/degradation optimization" game

import streamlit as st
import pandas as pd
import numpy as np
import time
import uuid
from datetime import datetime

# ----------------------------
# APP-WIDE CONSTANTS (edit me)
# ----------------------------
APP_TITLE = "Human Game Design – Degradation Optimization"
TARGET_HOURS = 3.0  # objective: complete degradation at ~3 hours
MAX_ENTRIES_PER_RUN = 5  # allow up to 5 per "batch" (paper-style)
WAVELENGTHS = np.arange(300, 801, 2)  # 300–800 nm UV-Vis window

SOLVENTS = ["2MeTHF", "Toluene", "Chloroform"]
POLYMER_CONCENTRATION = [0.05, 0.0]  # placeholder; not yet used
ACIDS = ["HCl", "TFA"]
ACID_CONCENTRATION = ["50x", "100x", "300x", "600x", "900x"]  # "x" relative to imine

# ----------------------------
# UTILS: SESSION & TIMER
# ----------------------------
def init_state():
    """Initialize session_state keys if absent."""
    ss = st.session_state
    ss.setdefault("page", "Survey")
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
    ss.page = "Experiment Builder"  # jump right back to builder for a fresh run

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

def simulate_uvvis(degradation_hours: float) -> np.ndarray:
    """
    Make a synthetic spectrum:
    - Start with a Gaussian 'π-π*' band; degrading shifts/lowers it.
    - More degraded (closer to target) -> lower peak intensity & slight red/blue shift.
    """
    lam = WAVELENGTHS
    diff = abs(degradation_hours - TARGET_HOURS)

    center = 550 + np.clip((TARGET_HOURS - degradation_hours) * 15, -25, 25)
    height = 1.0 / (1.0 + 0.4 * diff)  # lower when closer to target
    width = 60 + 10 * np.clip(diff, 0, 5)

    band = height * np.exp(-0.5 * ((lam - center) / width) ** 2)

    # add shoulder + baseline
    shoulder = 0.3 * height * np.exp(-0.5 * ((lam - (center + 110)) / (width + 30)) ** 2)
    baseline = 0.03 + 0.01 * np.sin(lam / 18.0)

    spectrum = band + shoulder + baseline + np.random.normal(0, 0.005, size=len(lam))
    return spectrum

# score: closeness to 3h (lower is better)
def closeness_score(hours: float) -> float:
    return float(np.round(abs(hours - TARGET_HOURS), 3))

# ----------------------------
# LAYOUT: SIDEBAR NAV + TIMER
# ----------------------------
def sidebar():
    # live time readout (it will tick because main() re-runs once/second while running)
    st.sidebar.markdown("### ⏱️ " + pretty_hms(elapsed_seconds()))

    # page navigation
    pages = [
        "Survey",
        "Instructions",
        "Experiment Builder",
        "Experiment Results",
        "Progress Tracker",
        "End Experiment",
    ]
    for p in pages:
        if st.sidebar.button(p, use_container_width=True):
            st.session_state.page = p
            if p == "Experiment Builder" and st.session_state.first_opened_builder_at is None:
                st.session_state.first_opened_builder_at = datetime.utcnow().isoformat()
                start_timer_if_needed()

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Tip: Timer starts when you first open *Experiment Builder* and stops on *End Experiment*."
    )

# ----------------------------
# PAGES
# ----------------------------
def page_survey():
    st.title("Survey")
    st.write("Please provide basic info. Consent is required to proceed.")

    # External link to your Terms/Consent page
    st.markdown(
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
        faculty = st.selectbox("Faculty", ["Undergraduate", "Graduate Student", "Postdoc", "Faculty/Staff", "Other"])
        experience = st.selectbox(
            "Experience in polymer chemistry", ["None", "< 1 year", "1–3 years", "3–5 years", "5+ years"]
        )

    consent = st.checkbox("I have read the Terms & Consent and I agree to participate.")

    if st.button("Save and Continue"):
        st.session_state.survey = dict(
            name=name, email=email, institution=inst, department=dept,
            faculty=faculty, experience=experience
        )
        st.session_state.consented = bool(consent)
        if not consent:
            st.warning("Consent is required to continue.")
        else:
            st.success("Consent recorded. Thank you!")
            st.session_state.page = "Instructions"
            st.rerun()

def page_instructions():
    st.title("Introduction & Game Rules")
    st.subheader("Purpose")
    st.write(
        "Your goal is to choose experimental conditions that produce **complete degradation** "
        f"as close as possible to **{TARGET_HOURS} hours**."
    )

    st.subheader("Rules")
    st.markdown(
        """
        - Build experiments on the **Experiment Builder** page.  
        - You can add multiple entries; run them to see results.  
        - Each run simulates spectra and a degradation time.  
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
    st.title("Experiment Builder")
    if not st.session_state.consented:
        st.warning("You must consent on the Survey page before playing.")
        return

    # First visit: start timer
    start_timer_if_needed()

    # Selection widgets
    st.subheader("Select Conditions and Add as Entries")
    c1, c2, c3 = st.columns(3)
    with c1:
        solvent = st.selectbox("Solvent", SOLVENTS, index=0)
    with c2:
        acid = st.selectbox("Acid Type", ACIDS, index=0)
    with c3:
        mult = st.selectbox(
            "Acid Concentration (*molar excess of imine)",
            ACID_CONCENTRATION,
            index=2
        )

    c4, c5 = st.columns([1, 1])
    with c4:
        if st.button("➕ Add Entry"):
            st.session_state.pending_entries.append(dict(
                entry_id=str(uuid.uuid4()),
                solvent=solvent,
                acid=acid,
                acid_mult=mult,
                added_at=datetime.utcnow().isoformat()
            ))
    with c5:
        if st.button("🧹 Clear Pending"):
            st.session_state.pending_entries = []

    # Show pending entries
    st.write("**Pending Entries (not yet run):**")
    if st.session_state.pending_entries:
        df = pd.DataFrame(st.session_state.pending_entries)
        st.dataframe(df, use_container_width=True)
    else:
        st.caption("No pending entries yet.")

    # ✅ Run limit message (only appears on this page now)
    st.markdown(f"**You can run up to {MAX_ENTRIES_PER_RUN} entries at a time.**")

    # Run button
    can_run = 0 < len(st.session_state.pending_entries) <= MAX_ENTRIES_PER_RUN
    if st.button("▶️ Run Experiments", disabled=not can_run):
        rows = []
        for e in st.session_state.pending_entries:
            hours = base_degradation_time(e["solvent"], e["acid"], e["acid_mult"])
            spec = simulate_uvvis(hours)  # numpy array
            rows.append(dict(
                session_id=st.session_state.session_id,
                entry_id=e["entry_id"],
                solvent=e["solvent"],
                acid=e["acid"],
                acid_mult=e["acid_mult"],
                degradation_hours=hours,
                closeness=closeness_score(hours),
                wavelengths=";".join(map(str, WAVELENGTHS.tolist())),
                absorbance=";".join(map(lambda x: f"{x:.4f}", spec.tolist())),
                run_at=datetime.utcnow().isoformat()
            ))
        st.session_state.results.extend(rows)
        st.session_state.pending_entries = []
        st.success("Run complete! Check **Experiment Results** or **Progress Tracker**.")

def page_results():
    st.title("Experiment Results")
    if not st.session_state.results:
        st.info("No results yet. Add entries and click **Run** on the Experiment Builder page.")
        return

    # Table of results
    df = pd.DataFrame(st.session_state.results)
    show_cols = ["entry_id", "solvent", "acid", "acid_mult", "degradation_hours", "closeness", "run_at"]
    st.dataframe(df[show_cols].sort_values("run_at"), use_container_width=True)

    st.markdown("---")
    st.subheader("View Spectrum for a Result")
    # pick an entry to plot
    entry_ids = [r["entry_id"] for r in st.session_state.results]
    sel = st.selectbox("Choose an entry", entry_ids)

    rec = next(r for r in st.session_state.results if r["entry_id"] == sel)
    # decode spectrum
    lam = np.array(list(map(float, rec["wavelengths"].split(";"))))
    absorb = np.array(list(map(float, rec["absorbance"].split(";"))))

    st.caption(
        f"Solvent: {rec['solvent']} | Acid: {rec['acid']} | Conc: {rec['acid_mult']} "
        f"| Degradation ~ {rec['degradation_hours']} h (closeness={rec['closeness']})"
    )

    # Plot with matplotlib (Streamlit integrates automatically)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot(lam, absorb)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Absorbance (a.u.)")
    ax.set_title("Simulated UV–Vis Spectrum")
    st.pyplot(fig)

def page_progress():
    st.title("Progress Tracker")
    if not st.session_state.results:
        st.info("No results yet. Run some experiments first.")
        return

    df = pd.DataFrame(st.session_state.results)
    best_idx = df["closeness"].idxmin()
    best = df.loc[best_idx]

    st.metric(label="Target (hours)", value=f"{TARGET_HOURS:.1f}")
    st.metric(label="Best so far (hours)", value=f"{best['degradation_hours']:.2f}")
    st.metric(label="Closeness (|best - target|, ↓ better)", value=f"{best['closeness']:.3f}")

    # simple bar of closeness
    st.write("### Closeness to Target")
    capped = float(np.clip(best["closeness"], 0, 5))
    pct = int((1 - capped / 5.0) * 100)
    st.progress(pct)

    # history chart (degradation hours across runs)
    st.write("### Degradation Time Across Results")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot(np.arange(1, len(df) + 1), df["degradation_hours"].astype(float), marker="o")
    ax.axhline(TARGET_HOURS, linestyle="--")
    ax.set_xlabel("Result #")
    ax.set_ylabel("Degradation time (h)")
    ax.set_title("History")
    st.pyplot(fig)

def page_end():
    st.title("End Experiment")
    if not st.session_state.ended:
        stop_timer()
        st.session_state.ended = True

    total_time = pretty_hms(elapsed_seconds())
    st.success(f"Experiment ended. Total time spent: {total_time}")

    # Assemble all data for export (survey + results)
    results = pd.DataFrame(st.session_state.results)
    if not results.empty:
        results = results.assign(
            participant_name=st.session_state.survey.get("name", ""),
            participant_email=st.session_state.survey.get("email", ""),
            session_id=st.session_state.session_id,
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
    else:
        st.info("No experiment results to export.")

    st.markdown("---")
    # Optional: New Attempt button (resets state and goes back to Builder)
    if st.button("🔁 New Attempt (clear results & restart timer)", use_container_width=True):
        reset_for_new_attempt()
        st.rerun()

    st.caption("You can start a new attempt above or close the app.")

# ----------------------------
# MAIN
# ----------------------------
def main():
    # Keep this at the top
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_state()

    # Render UI
    sidebar()
    st.markdown(f"# {APP_TITLE}")

    # Router
    page = st.session_state.page
    if page == "Survey":
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
        page_survey()

    # 🔁 After rendering everything, schedule a tick if the timer is running
    if st.session_state.get("timer_running", False) and not st.session_state.get("ended", False):
        time.sleep(1)
        st.rerun()

if __name__ == "__main__":
    main()
