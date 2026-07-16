from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st

from project.manager import create_project, list_projects, open_project, create_experiment
from utils.json_io import load_json, save_json
from core.dpv import parse_concentration as parse_dpv_concentration, run_dpv_analysis
from core.swv import parse_concentration as parse_swv_concentration, run_swv_analysis
from core.eis import parse_concentration as parse_eis_concentration, run_eis_analysis
from core.cv import parse_scan_rate, run_cv_analysis
from figures.builder import collect_figure_files, make_composite_figure, suggest_next_figure_name, PPTX_AVAILABLE
from database.db import init_database, add_record, get_table, get_names, seed_default_database
from statistics.replicate import run_statistics_analysis
from utils.backup import create_project_backup
from eln.notebook import load_entries, add_entry, delete_entry, entries_dataframe, export_markdown
from quick.workspace import (
    save_uploaded_files,
    save_quick_note,
    build_inventory,
    get_analysis_status,
    recent_figures,
    export_experiment_zip,
)

from smart_experiment.manager import (
    infer_source_folder_name,
    sanitize_experiment_name,
    build_concentration_preview,
    update_records_and_concentrations,
    create_or_open_smart_experiment,
    save_concentration_tables,
    update_experiment_smart_metadata,
)

from smart_import.folder_import import (
    CATEGORY_DESTINATIONS,
    uploaded_files_to_records,
    zip_upload_to_records,
    records_preview_dataframe,
    update_records_from_preview,
    import_records,
)

from history.analysis_history import (
    scan_project_history,
    filter_history,
    compact_history_table,
)

from summary.experiment_summary import (
    latest_result_table,
    latest_method_figure,
    latest_delta_peak_table,
    compact_latest_values,
    experiment_counts,
    latest_eln_entry,
    create_html_report,
)

from plugins.auto_analyzer import (
    available_methods,
    build_method_table,
    run_selected_methods,
    summary_dataframe,
    save_auto_analysis_log,
)

from workspace.results import (
    collect_result_files,
    read_result_table,
    collect_figures,
    batch_summary,
    generate_discussion,
)

st.set_page_config(page_title="EC Research Studio", layout="wide")
st.title("EC Research Studio v1.8.0 Smart Experiment")
st.caption("Integrated electrochemical research platform: DPV / SWV / EIS / CV / Statistics / Figures")

st.sidebar.header("Project")
mode = st.sidebar.radio("Mode", ["New Project", "Open Project"])

if mode == "New Project":
    project_name = st.sidebar.text_input("Project name", value="RNA_Aptamer_Test")
    if st.sidebar.button("Create Project"):
        project_path = create_project(project_name)
        st.sidebar.success("Project created")
        st.sidebar.code(str(project_path))

projects = list_projects()
if not projects:
    st.info("왼쪽에서 New Project를 먼저 만들어줘.")
    st.stop()

selected_project = st.sidebar.selectbox("Select project", projects)
project_path, project_info = open_project(selected_project)
init_database(project_path)
st.header(f"Project: {project_info['project_name']}")

PAGE_OPTIONS = [
    "Smart Experiment",
    "Today",
    "Analysis History",
    "Experiment Summary",
    "Auto Analyze",
    "Results",
    "Dashboard",
    "Experiments",
    "Experiment Wizard",
    "Database",
    "Raw Data Import",
    "DPV Analysis",
    "SWV Analysis",
    "EIS Analysis",
    "CV Analysis",
    "Statistics",
    "Figure Builder",
    "ELN",
    "Project Info",
]

st.sidebar.markdown("## EC Research Studio")
st.sidebar.markdown("### Navigation")
selected_page = st.sidebar.radio(
    "Open page",
    PAGE_OPTIONS,
    index=0,
    key="main_navigation",
)

st.sidebar.markdown("---")
st.sidebar.caption("Only the selected page is rendered.")





if selected_page == "Smart Experiment":
    st.subheader("Smart Experiment")
    st.caption(
        "Upload one concentration-series folder or ZIP. The folder name becomes "
        "the Experiment name, files are classified automatically, and concentrations "
        "are extracted from filenames."
    )

    input_mode = st.radio(
        "Input format",
        ["Folder upload", "ZIP upload"],
        horizontal=True,
        key="smart_exp_input_mode",
    )

    if input_mode == "Folder upload":
        smart_exp_folder_files = st.file_uploader(
            "Drag the complete concentration-series folder here",
            accept_multiple_files="directory",
            key="smart_exp_folder_upload",
        )
        smart_exp_records = uploaded_files_to_records(smart_exp_folder_files)
    else:
        smart_exp_zip = st.file_uploader(
            "Drag the concentration-series ZIP here",
            type=["zip"],
            accept_multiple_files=False,
            key="smart_exp_zip_upload",
        )
        try:
            smart_exp_records = zip_upload_to_records(smart_exp_zip)
        except Exception as e:
            st.error(f"ZIP file could not be read: {e}")
            smart_exp_records = []

    if not smart_exp_records:
        st.info("Upload a folder or ZIP to create a Smart Experiment.")
    else:
        source_folder_name = infer_source_folder_name(
            smart_exp_records,
            fallback="Smart_Experiment",
        )
        suggested_name = sanitize_experiment_name(source_folder_name)

        st.write("### 1. Experiment name")
        experiment_name = st.text_input(
            "Suggested Experiment name",
            value=suggested_name,
            key="smart_exp_name",
        )

        collision_policy = st.selectbox(
            "If an Experiment with the same name already exists",
            [
                "Create new with timestamp",
                "Use existing",
                "Cancel",
            ],
            index=0,
            key="smart_exp_collision",
        )

        st.write("### 2. File classification")
        classification_df = records_preview_dataframe(smart_exp_records)
        edited_classification = st.data_editor(
            classification_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "Record ID",
                "Original path",
                "File",
                "Detected type",
                "Destination",
                "Size (KB)",
                "Source",
            ],
            column_config={
                "Selected type": st.column_config.SelectboxColumn(
                    "Selected type",
                    options=[
                        "DPV",
                        "SWV",
                        "EIS",
                        "CV",
                        "Images",
                        "Other",
                        "Review required",
                    ],
                    required=True,
                )
            },
            key="smart_exp_classification",
        )
        classified_records = update_records_from_preview(
            smart_exp_records,
            edited_classification,
        )

        st.write("### 3. Concentration recognition")
        concentration_preview = build_concentration_preview(classified_records)

        if concentration_preview.empty:
            st.warning("No DPV, SWV, or EIS files are currently classified.")
            edited_concentrations = concentration_preview
        else:
            edited_concentrations = st.data_editor(
                concentration_preview,
                use_container_width=True,
                hide_index=True,
                disabled=[
                    "Record ID",
                    "Method",
                    "File",
                    "Original path",
                    "Detected unit",
                    "Detection status",
                ],
                column_config={
                    "Concentration_pM": st.column_config.NumberColumn(
                        "Concentration (pM)",
                        min_value=0.0,
                        format="%.6g",
                    )
                },
                key="smart_exp_concentrations",
            )

            review_count = int(
                pd.to_numeric(
                    edited_concentrations["Concentration_pM"],
                    errors="coerce",
                ).isna().sum()
            )
            if review_count:
                st.warning(
                    f"{review_count} concentration value(s) require review. "
                    "Enter pM values before Auto Analyze."
                )

        st.write("### 4. Create, import, and analyze")
        c1, c2 = st.columns(2)
        duplicate_policy = c1.selectbox(
            "Duplicate file policy",
            ["Rename with timestamp", "Skip", "Overwrite"],
            index=0,
            key="smart_exp_duplicate",
        )
        run_auto = c2.checkbox(
            "Run Auto Analyze",
            value=True,
            key="smart_exp_auto",
        )

        with st.expander("DPV search settings", expanded=False):
            dpv_peak_min = st.number_input(
                "Peak search start (V)",
                value=0.30,
                step=0.01,
                format="%.3f",
                key="smart_exp_dpv_peak_min",
            )
            dpv_peak_max = st.number_input(
                "Peak search end (V)",
                value=0.70,
                step=0.01,
                format="%.3f",
                key="smart_exp_dpv_peak_max",
            )
            dpv_baseline_min = st.number_input(
                "Minimum search start (V)",
                value=0.05,
                step=0.01,
                format="%.3f",
                key="smart_exp_dpv_baseline_min",
            )
            dpv_smoothing = st.number_input(
                "Detection smoothing window",
                min_value=5,
                max_value=101,
                value=11,
                step=2,
                key="smart_exp_dpv_smoothing",
            )

        if st.button(
            "Create Smart Experiment",
            type="primary",
            key="smart_exp_create",
        ):
            final_records = update_records_and_concentrations(
                classified_records,
                edited_concentrations,
            )

            unresolved = [
                record["File"]
                for record in final_records
                if record.get("Selected type") in ["DPV", "SWV", "EIS"]
                and record.get("Concentration_pM") is None
            ]

            if run_auto and unresolved:
                st.error(
                    "Auto Analyze was not started because these files have no "
                    f"confirmed concentration: {', '.join(unresolved)}"
                )
            else:
                exp_path, create_action = create_or_open_smart_experiment(
                    project_path=project_path,
                    project_info=project_info,
                    experiment_name=experiment_name,
                    collision_policy=collision_policy,
                    metadata={
                        "source_folder_name": source_folder_name,
                        "created_from": input_mode,
                    },
                )

                if exp_path is None:
                    st.info("Smart Experiment creation was cancelled.")
                else:
                    import_result = import_records(
                        exp_path,
                        final_records,
                        duplicate_policy=duplicate_policy,
                    )
                    concentration_info = save_concentration_tables(
                        exp_path,
                        final_records,
                    )

                    completed = []
                    failed = []
                    auto_summary = None

                    imported_methods = [
                        method
                        for method in ["DPV", "SWV", "EIS", "CV"]
                        if method in set(
                            import_result["log_df"]
                            .loc[
                                import_result["log_df"]["Status"]
                                != "Skipped duplicate",
                                "Selected type",
                            ]
                            .astype(str)
                        )
                    ]

                    if run_auto and imported_methods:
                        with st.spinner("Running Auto Analyze..."):
                            completed, failed = run_selected_methods(
                                exp_path=exp_path,
                                methods=imported_methods,
                                use_abs_fit=True,
                                dpv_baseline_mode="preceding_local_minimum",
                                dpv_peak_search_min_v=float(dpv_peak_min),
                                dpv_peak_search_max_v=float(dpv_peak_max),
                                dpv_baseline_search_min_v=float(dpv_baseline_min),
                                dpv_smoothing_window=int(dpv_smoothing),
                            )
                        auto_summary = summary_dataframe(completed, failed)
                        save_auto_analysis_log(exp_path, auto_summary)

                    update_experiment_smart_metadata(
                        exp_path=exp_path,
                        source_name=source_folder_name,
                        concentration_table_info=concentration_info,
                        import_result=import_result,
                        auto_analysis_summary=auto_summary,
                    )

                    st.success(
                        f"Smart Experiment ready: {exp_path.name} "
                        f"({create_action})"
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric(
                        "DPV",
                        int(
                            (
                                import_result["log_df"]["Selected type"]
                                == "DPV"
                            ).sum()
                        ),
                    )
                    m2.metric(
                        "SWV",
                        int(
                            (
                                import_result["log_df"]["Selected type"]
                                == "SWV"
                            ).sum()
                        ),
                    )
                    m3.metric(
                        "EIS",
                        int(
                            (
                                import_result["log_df"]["Selected type"]
                                == "EIS"
                            ).sum()
                        ),
                    )
                    m4.metric(
                        "Concentrations",
                        int(
                            concentration_info["all_table"][
                                "Concentration_pM"
                            ].nunique(dropna=True)
                        )
                        if not concentration_info["all_table"].empty
                        else 0,
                    )

                    st.write("#### Concentration tables")
                    st.dataframe(
                        concentration_info["all_table"],
                        use_container_width=True,
                        hide_index=True,
                    )
                    if concentration_info["all_csv"] is not None:
                        st.code(str(concentration_info["all_csv"]))

                    if auto_summary is not None:
                        st.write("#### Auto Analyze summary")
                        st.dataframe(
                            auto_summary,
                            use_container_width=True,
                            hide_index=True,
                        )

                    recent = recent_figures(exp_path, limit=8)
                    if recent:
                        st.write("#### Generated graphs")
                        cols = st.columns(4)
                        for i, fig_path in enumerate(recent):
                            with cols[i % 4]:
                                st.image(
                                    str(fig_path),
                                    caption=fig_path.name,
                                    use_container_width=True,
                                )

                    st.code(str(exp_path))


if selected_page == "Today":
    st.subheader("Today's Experiment")

    experiments = project_info.get("experiments", [])

    if not experiments:
        st.info("먼저 Experiments 또는 Experiment Wizard 탭에서 실험을 생성해줘.")
    else:
        selected_exp_today = st.selectbox("Experiment", experiments, key="today_exp")
        exp_path = Path(project_path) / "Experiments" / selected_exp_today

        status = get_analysis_status(exp_path)
        inventory = build_inventory(exp_path)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Files", len(inventory))
        c2.metric("Raw data", int(inventory["Category"].astype(str).str.contains("raw").sum()) if not inventory.empty else 0)
        c3.metric("Figures", int((inventory["Category"] == "Figure").sum()) if not inventory.empty else 0)
        c4.metric("Notes", int((inventory["Category"] == "Note").sum()) if not inventory.empty else 0)

        st.write("### Analysis status")
        status_df = pd.DataFrame([
            {
                "Method": method,
                "Raw files": info["raw_count"],
                "Result files": info["result_count"],
                "Status": info["state"]
            }
            for method, info in status.items()
        ])
        st.dataframe(status_df, use_container_width=True)

        smart_tab, import_tab, note_tab, preview_tab, inventory_tab, export_tab = st.tabs([
            "Smart Folder Import",
            "Manual Import",
            "Quick Note",
            "Recent Figures",
            "Inventory",
            "Export"
        ])


        with smart_tab:
            st.write("### Import a complete experiment folder")
            st.caption(
                "Drop the whole folder or a ZIP file. Native files are classified by extension: "
                ".mtd → DPV, .mts → SWV, .mteisp → EIS."
            )

            input_mode = st.radio(
                "Input format",
                ["Folder upload", "ZIP upload"],
                horizontal=True,
                key="smart_import_mode",
            )

            folder_files = []
            zip_file = None

            if input_mode == "Folder upload":
                folder_files = st.file_uploader(
                    "Drag the experiment folder here",
                    accept_multiple_files="directory",
                    key="smart_folder_files",
                    help="Select or drag a folder containing all files from today's experiment.",
                )
                smart_records = uploaded_files_to_records(folder_files)
            else:
                zip_file = st.file_uploader(
                    "Drag the experiment ZIP here",
                    type=["zip"],
                    accept_multiple_files=False,
                    key="smart_zip_file",
                )
                try:
                    smart_records = zip_upload_to_records(zip_file)
                except Exception as e:
                    st.error(f"ZIP file could not be read: {e}")
                    smart_records = []

            if smart_records:
                detected_preview = records_preview_dataframe(smart_records)

                st.write("#### Classification summary")
                summary_counts = (
                    detected_preview["Detected type"]
                    .value_counts()
                    .rename_axis("Detected type")
                    .reset_index(name="Files")
                )
                st.dataframe(summary_counts, use_container_width=True, hide_index=True)

                st.write("#### Review before import")
                st.caption(
                    "CSV files are marked Review required because the measurement type "
                    "cannot be determined from the extension alone."
                )

                edited_preview = st.data_editor(
                    detected_preview,
                    use_container_width=True,
                    hide_index=True,
                    disabled=[
                        "Record ID",
                        "Original path",
                        "File",
                        "Detected type",
                        "Destination",
                        "Size (KB)",
                        "Source",
                    ],
                    column_config={
                        "Selected type": st.column_config.SelectboxColumn(
                            "Selected type",
                            options=[
                                "DPV",
                                "SWV",
                                "EIS",
                                "CV",
                                "Images",
                                "Other",
                                "Review required",
                            ],
                            required=True,
                        )
                    },
                    key="smart_import_preview",
                )

                duplicate_policy = st.selectbox(
                    "When a file with the same name already exists",
                    ["Rename with timestamp", "Skip", "Overwrite"],
                    index=0,
                    key="smart_duplicate_policy",
                )

                run_after_import = st.checkbox(
                    "Run Auto Analyze after import",
                    value=False,
                    key="smart_run_auto_analyze",
                    help="Only DPV, SWV, EIS, and CV files imported into RawData are analyzed.",
                )

                if st.button(
                    "Classify and save to Experiment",
                    type="primary",
                    key="smart_import_save",
                ):
                    final_records = update_records_from_preview(
                        smart_records,
                        edited_preview,
                    )

                    if any(
                        record.get("Selected type") == "Review required"
                        for record in final_records
                    ):
                        st.warning(
                            "Review required files will be stored in "
                            "Attachments/ReviewRequired. Change their Selected type "
                            "before import when the method is known."
                        )

                    result = import_records(
                        exp_path,
                        final_records,
                        duplicate_policy=duplicate_policy,
                    )

                    st.success(
                        f"{len(result['log_df'])} file(s) processed and classified."
                    )
                    st.dataframe(
                        result["counts_df"],
                        use_container_width=True,
                        hide_index=True,
                    )

                    with st.expander("Import log", expanded=False):
                        st.dataframe(
                            result["log_df"],
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.code(str(result["log_csv"]))
                        st.code(str(result["metadata_path"]))

                    if run_after_import:
                        imported_methods = [
                            method
                            for method in ["DPV", "SWV", "EIS", "CV"]
                            if method in set(
                                result["log_df"]
                                .loc[
                                    result["log_df"]["Status"] != "Skipped duplicate",
                                    "Selected type",
                                ]
                                .astype(str)
                            )
                        ]

                        if imported_methods:
                            with st.spinner("Running Auto Analyze..."):
                                completed, failed = run_selected_methods(
                                    exp_path=exp_path,
                                    methods=imported_methods,
                                    use_abs_fit=True,
                                )

                            auto_summary = summary_dataframe(completed, failed)
                            auto_log_csv, auto_log_txt = save_auto_analysis_log(
                                exp_path,
                                auto_summary,
                            )

                            st.write("#### Auto Analyze result")
                            st.dataframe(
                                auto_summary,
                                use_container_width=True,
                                hide_index=True,
                            )
                            st.code(str(auto_log_csv))
                            st.code(str(auto_log_txt))
                        else:
                            st.info(
                                "No DPV, SWV, EIS, or CV files were available "
                                "for Auto Analyze."
                            )
            else:
                st.info(
                    "Upload a folder or ZIP to preview automatic classification."
                )

        with import_tab:
            category = st.selectbox(
                "File category",
                ["DPV", "SWV", "EIS", "CV", "Images", "Other"],
                key="today_category"
            )

            type_map = {
                "DPV": ["mtd", "csv", "txt", "xlsx"],
                "SWV": ["mts", "csv", "txt", "xlsx"],
                "EIS": ["mteisp", "csv", "txt", "xlsx"],
                "CV": ["csv", "txt", "xlsx"],
                "Images": ["png", "jpg", "jpeg", "webp", "tif", "tiff"],
                "Other": ["pdf", "docx", "pptx", "txt", "csv", "xlsx", "zip"]
            }

            files = st.file_uploader(
                "Drag and drop files",
                type=type_map[category],
                accept_multiple_files=True,
                key="today_files"
            )

            if files:
                st.dataframe(pd.DataFrame([
                    {
                        "File": f.name,
                        "Category": category,
                        "Size (KB)": round(f.size / 1024, 2)
                    }
                    for f in files
                ]), use_container_width=True)

            if st.button("Save to experiment", type="primary", key="today_save_files"):
                saved = save_uploaded_files(exp_path, category, files)
                if saved:
                    st.success(f"{len(saved)} file(s) saved.")
                    st.dataframe(pd.DataFrame(saved), use_container_width=True)
                else:
                    st.warning("선택한 파일이 없습니다.")

        with note_tab:
            observation = st.text_area("Observation", height=120, key="today_observation")
            result = st.text_area("Result", height=120, key="today_result")
            next_action = st.text_area("Next experiment / action", height=100, key="today_next")

            if st.button("Save quick note", type="primary", key="today_save_note"):
                note_path = save_quick_note(exp_path, observation, result, next_action)
                st.success("Quick note saved.")
                st.code(str(note_path))

        with preview_tab:
            figures = recent_figures(exp_path)

            if not figures:
                st.info("아직 생성된 Figure가 없습니다.")
            else:
                cols = st.columns(3)
                for i, fig_path in enumerate(figures):
                    with cols[i % 3]:
                        st.image(str(fig_path), caption=fig_path.name, use_container_width=True)

        with inventory_tab:
            inventory = build_inventory(exp_path)

            if inventory.empty:
                st.info("저장된 파일이 없습니다.")
            else:
                categories = ["All"] + sorted(inventory["Category"].dropna().unique().tolist())
                selected_category = st.selectbox("Filter", categories, key="today_inventory_filter")
                view_df = inventory if selected_category == "All" else inventory[inventory["Category"] == selected_category]
                st.dataframe(view_df, use_container_width=True)

                st.download_button(
                    "Download inventory CSV",
                    data=view_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{selected_exp_today}_inventory.csv",
                    mime="text/csv",
                    key="today_inventory_download"
                )

        with export_tab:
            st.write("현재 Experiment의 원본 데이터, 결과, Figure, Note를 ZIP으로 내보냅니다.")

            if st.button("Create experiment ZIP", type="primary", key="today_export"):
                zip_path = export_experiment_zip(exp_path)
                st.success("Experiment ZIP created.")

                with open(zip_path, "rb") as f:
                    st.download_button(
                        "Download experiment ZIP",
                        data=f.read(),
                        file_name=zip_path.name,
                        mime="application/zip",
                        key="today_download_zip"
                    )






if selected_page == "Analysis History":
    st.subheader("Analysis History")
    st.caption("프로젝트의 Experiment와 분석 결과 이력을 검색하고 최근 결과를 확인합니다.")
    history_df = scan_project_history(project_path)
    if history_df.empty:
        st.info("현재 프로젝트에서 분석 이력을 찾지 못했습니다.")
    else:
        c1, c2, c3 = st.columns([1.8, 1, 1])
        keyword = c1.text_input("Search", value="", placeholder="Experiment, target, file name, ELN keyword, concentration...", key="history_keyword")
        method_filter = c2.selectbox("Method", ["All", "DPV", "SWV", "EIS", "CV"], key="history_method")
        sort_order = c3.selectbox("Sort", ["Latest first", "Oldest first"], key="history_sort")
        filtered_history = filter_history(history_df, keyword=keyword, method=method_filter, sort_order=sort_order)
        st.write("### History table")
        compact = compact_history_table(filtered_history)
        st.dataframe(compact, use_container_width=True, hide_index=True)
        st.download_button("Download filtered history CSV", data=compact.to_csv(index=False).encode("utf-8-sig"), file_name="analysis_history.csv", mime="text/csv", key="history_download")
        if filtered_history.empty:
            st.info("현재 검색 조건과 일치하는 분석 이력이 없습니다.")
        else:
            labels=[f"{r['Experiment']} | {r['Method']} | {r['Latest activity']}" for _,r in filtered_history.iterrows()]
            selected=st.selectbox("Open history record",labels,key="history_open_record")
            record=filtered_history.iloc[labels.index(selected)].to_dict()
            st.write("### Record preview")
            m1,m2,m3,m4=st.columns(4)
            m1.metric("Method",record.get("Method","")); m2.metric("Raw files",int(record.get("Raw files",0))); m3.metric("Result files",int(record.get("Result files",0))); m4.metric("Figures",int(record.get("Figures",0)))
            left,right=st.columns([1,1.35])
            with left:
                st.write(f"**Experiment:** {record.get('Experiment','')}")
                st.write(f"**Latest activity:** {record.get('Latest activity','')}")
                st.write(f"**Target:** {record.get('Target','')}")
                st.write(f"**Sensor:** {record.get('Sensor','')}")
                st.write(f"**Researcher:** {record.get('Researcher','')}")
                st.write(f"**Key result:** {record.get('Key result','')}")
                if record.get('Latest result path'): st.code(record['Latest result path'])
                if record.get('Latest report path'): st.code(record['Latest report path'])
                st.code(record.get('Experiment path',''))
            with right:
                fp=record.get('Latest figure path','')
                if fp and Path(fp).exists():
                    st.image(fp,caption=Path(fp).name,use_container_width=True)
                    with open(fp,'rb') as f: st.download_button('Download latest figure',data=f.read(),file_name=Path(fp).name,mime='image/png',key='history_figure_download')
                else: st.info('이 기록에 표시할 Figure가 없습니다.')
            rp=record.get('Latest result path','')
            if rp and Path(rp).exists():
                st.write('### Latest result preview')
                try:
                    preview=pd.read_excel(rp) if Path(rp).suffix.lower()=='.xlsx' else pd.read_csv(rp)
                    st.dataframe(preview.tail(12),use_container_width=True)
                except Exception as e: st.warning(f'Result preview를 읽지 못했습니다: {e}')

if selected_page == "Experiment Summary":
    st.subheader("Experiment Summary")
    st.caption("가장 최근 결과값, 최신 전기화학 그래프, ΔPeak 값을 한 화면에서 확인합니다.")

    experiments = project_info.get("experiments", [])

    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_summary = st.selectbox(
            "Experiment",
            experiments,
            key="summary_exp",
        )
        exp_path = Path(project_path) / "Experiments" / selected_exp_summary

        latest_method, latest_path, latest_df = latest_result_table(exp_path)
        graph_method, graph_path = latest_method_figure(
            exp_path,
            preferred_method=latest_method,
        )
        delta_method, delta_path, delta_df = latest_delta_peak_table(
            exp_path,
            preferred_method=latest_method,
        )

        counts_df = experiment_counts(exp_path)
        total_raw = int(counts_df["Raw files"].sum())
        total_results = int(counts_df["Result files"].sum())
        total_figures = int(counts_df["Figures"].sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Raw files", total_raw)
        c2.metric("Result files", total_results)
        c3.metric("Figures", total_figures)
        c4.metric("Latest method", latest_method or "None")

        st.write("### Analysis status")
        st.dataframe(counts_df, use_container_width=True)

        left, right = st.columns([1.1, 1.4])

        with left:
            st.write("### Latest updated result")
            if latest_df is None or latest_df.empty:
                st.info("최근 결과 테이블이 없습니다.")
            else:
                st.caption(f"{latest_method} | {Path(latest_path).name}")
                latest_values = compact_latest_values(latest_df, max_rows=10)
                st.dataframe(latest_values, use_container_width=True)

                st.download_button(
                    "Download latest values CSV",
                    data=latest_values.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{selected_exp_summary}_latest_values.csv",
                    mime="text/csv",
                    key="summary_latest_values_download",
                )

            st.write("### Latest ΔPeak values")
            if delta_df is None or delta_df.empty:
                st.info("DPV 또는 SWV ΔPeak 결과가 없습니다.")
            else:
                st.caption(f"{delta_method} | {Path(delta_path).name}")
                delta_values = compact_latest_values(delta_df, max_rows=12)
                st.dataframe(delta_values, use_container_width=True)

                st.download_button(
                    "Download ΔPeak CSV",
                    data=delta_values.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{selected_exp_summary}_{delta_method}_delta_peak.csv",
                    mime="text/csv",
                    key="summary_delta_download",
                )

        with right:
            st.write("### Latest electrochemical graph")
            if graph_path is None:
                st.info("표시할 DPV, SWV, EIS 또는 CV Figure가 없습니다.")
            else:
                st.caption(f"{graph_method} | {graph_path.name}")
                st.image(
                    str(graph_path),
                    use_container_width=True,
                )

                with open(graph_path, "rb") as f:
                    st.download_button(
                        "Download graph PNG",
                        data=f.read(),
                        file_name=graph_path.name,
                        mime="image/png",
                        key="summary_graph_download",
                    )

        st.write("### Latest ELN note")
        latest_note = latest_eln_entry(exp_path)
        if latest_note is None:
            st.info("저장된 ELN note가 없습니다.")
        else:
            st.write(f"**{latest_note.get('title', '')}**")
            st.caption(latest_note.get("created_at", ""))
            st.write(latest_note.get("result_summary", ""))

        if st.button(
            "Create HTML Experiment Report",
            type="primary",
            key="summary_html_create",
        ):
            html_path = create_html_report(
                exp_path=exp_path,
                experiment_name=selected_exp_summary,
                latest_method=latest_method,
                latest_result_path=latest_path,
                latest_result_df=latest_df,
                graph_method=graph_method,
                graph_path=graph_path,
                delta_method=delta_method,
                delta_path=delta_path,
                delta_df=delta_df,
            )

            st.success("HTML experiment report created.")

            with open(html_path, "rb") as f:
                st.download_button(
                    "Download HTML report",
                    data=f.read(),
                    file_name=html_path.name,
                    mime="text/html",
                    key="summary_html_download",
                )


if selected_page == "Auto Analyze":
    st.subheader("Auto Analyzer")
    st.caption("Instrument raw files (.mtd/.mts/.mteisp) and CSV files are analyzed directly. When multiple curves are stored, the last measurement curve is used.")

    experiments = project_info.get("experiments", [])

    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_auto = st.selectbox(
            "Experiment",
            experiments,
            key="auto_exp",
        )
        exp_path = Path(project_path) / "Experiments" / selected_exp_auto

        detected_methods = available_methods(exp_path)

        if not detected_methods:
            st.warning("분석 가능한 CSV 파일이 없습니다. Today 또는 Raw Data Import에서 파일을 먼저 저장해줘.")
        else:
            st.write("### Detected raw data")
            detected_rows = []

            for method in detected_methods:
                table = build_method_table(exp_path, method)
                detected_rows.append({
                    "Method": method,
                    "CSV files": len(table),
                })

            st.dataframe(
                pd.DataFrame(detected_rows),
                use_container_width=True,
            )

            selected_methods = st.multiselect(
                "Methods to analyze",
                ["DPV", "SWV", "EIS", "CV"],
                default=detected_methods,
                key="auto_methods",
            )

            use_abs_fit_auto = st.checkbox(
                "Use absolute value for concentration fitting",
                value=True,
                key="auto_abs_fit",
            )

            with st.expander("DPV peak and baseline settings", expanded=("DPV" in selected_methods)):
                dpv_mode_label = st.selectbox(
                    "DPV baseline mode",
                    [
                        "Shape-based: local minimum before main peak",
                        "Legacy: fixed potential region ≤ 0 V",
                    ],
                    index=0,
                    key="auto_dpv_mode",
                )

                c1, c2, c3 = st.columns(3)
                auto_peak_min = c1.number_input(
                    "Peak search start (V)",
                    value=0.30,
                    step=0.01,
                    format="%.3f",
                    key="auto_peak_min",
                )
                auto_peak_max = c2.number_input(
                    "Peak search end (V)",
                    value=0.70,
                    step=0.01,
                    format="%.3f",
                    key="auto_peak_max",
                )
                auto_baseline_min = c3.number_input(
                    "Minimum search start (V)",
                    value=0.05,
                    step=0.01,
                    format="%.3f",
                    key="auto_baseline_min",
                )
                auto_smoothing = st.number_input(
                    "Detection smoothing window",
                    min_value=5,
                    max_value=101,
                    value=11,
                    step=2,
                    key="auto_smoothing",
                )

            if st.button(
                "Run selected analyses",
                type="primary",
                key="auto_run",
            ):
                if not selected_methods:
                    st.warning("분석 방법을 하나 이상 선택해줘.")
                else:
                    dpv_mode = (
                        "preceding_local_minimum"
                        if dpv_mode_label.startswith("Shape-based")
                        else "fixed_region"
                    )

                    with st.spinner("Running selected analyses..."):
                        completed, failed = run_selected_methods(
                            exp_path=exp_path,
                            methods=selected_methods,
                            use_abs_fit=use_abs_fit_auto,
                            dpv_baseline_mode=dpv_mode,
                            dpv_peak_search_min_v=auto_peak_min,
                            dpv_peak_search_max_v=auto_peak_max,
                            dpv_baseline_search_min_v=auto_baseline_min,
                            dpv_smoothing_window=auto_smoothing,
                        )

                    summary_df = summary_dataframe(completed, failed)
                    csv_log, txt_log = save_auto_analysis_log(
                        exp_path,
                        summary_df,
                    )

                    exp_json = exp_path / "experiment.json"
                    if exp_json.exists():
                        exp_info = load_json(exp_json)
                        exp_info.setdefault("results", [])

                        for item in completed:
                            exp_info["results"].append({
                                "analysis": item["Method"],
                                "created_at": item["Completed at"],
                                "result_dir": item["Result directory"],
                                "figure_dir": item["Figure directory"],
                                "report_dir": item["Report directory"],
                                "source": "Auto Analyzer",
                            })

                        save_json(exp_json, exp_info)

                    st.write("### Auto-analysis summary")
                    st.dataframe(summary_df, use_container_width=True)

                    if completed:
                        st.success(f"{len(completed)} analysis method(s) completed.")

                    if failed:
                        st.warning(f"{len(failed)} method(s) failed or were skipped. Check the Message column.")

                    st.write("### Log files")
                    st.code(str(csv_log))
                    st.code(str(txt_log))

                    recent = recent_figures(exp_path, limit=8)
                    if recent:
                        st.write("### Newly available figures")
                        cols = st.columns(4)
                        for i, fig_path in enumerate(recent):
                            with cols[i % 4]:
                                st.image(
                                    str(fig_path),
                                    caption=fig_path.name,
                                    use_container_width=True,
                                )


if selected_page == "Results":
    st.subheader("Results")
    experiments = project_info.get("experiments", [])
    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_results = st.selectbox("Experiment", experiments, key="results_exp")
        exp_path = Path(project_path) / "Experiments" / selected_exp_results
        st.dataframe(batch_summary(exp_path), use_container_width=True)

        table_tab, figure_tab, discussion_tab = st.tabs(["Result tables", "Figure gallery", "Discussion draft"])

        with table_tab:
            files = collect_result_files(exp_path)
            if not files:
                st.info("결과 파일이 없습니다.")
            else:
                labels = [f"[{x['method']}] {x['label']}" for x in files]
                selected = st.selectbox("Result file", labels, key="result_file")
                item = files[labels.index(selected)]
                df = read_result_table(item["path"])
                st.dataframe(df, use_container_width=True)
                st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name=Path(item["path"]).stem+"_export.csv", mime="text/csv")

        with figure_tab:
            figs = collect_figures(exp_path)
            if not figs:
                st.info("Figure가 없습니다.")
            else:
                cols = st.columns(3)
                for i, item in enumerate(figs[:12]):
                    with cols[i % 3]:
                        st.image(item["path"], caption=f"[{item['method']}] {Path(item['path']).name}", use_container_width=True)

        with discussion_tab:
            files = collect_result_files(exp_path)
            if not files:
                st.info("Discussion 초안을 만들 결과 파일이 없습니다.")
            else:
                labels = [f"[{x['method']}] {x['label']}" for x in files]
                selected = st.selectbox("Source result", labels, key="discussion_source")
                item = files[labels.index(selected)]
                if st.button("Generate Discussion Draft", type="primary", key="discussion_generate"):
                    df = read_result_table(item["path"])
                    draft = generate_discussion(item["method"], df)
                    st.text_area("Discussion draft", value=draft, height=300)
                    st.download_button("Download draft", draft.encode("utf-8"), file_name=f"{selected_exp_results}_{item['method']}_discussion.txt", mime="text/plain")


if selected_page == "Dashboard":
    st.subheader("Project Dashboard")

    experiments = project_info.get("experiments", [])
    total_experiments = len(experiments)

    analysis_counts = {"DPV": 0, "SWV": 0, "EIS": 0, "CV": 0}
    figure_count = 0

    for exp_name in experiments:
        exp_path = Path(project_path) / "Experiments" / exp_name
        exp_json = exp_path / "experiment.json"

        if exp_json.exists():
            exp_info = load_json(exp_json)
            for item in exp_info.get("results", []):
                method = item.get("analysis")
                if method in analysis_counts:
                    analysis_counts[method] += 1

        pub_dir = exp_path / "PublicationFigures"
        if pub_dir.exists():
            figure_count += len([p for p in pub_dir.iterdir() if p.is_dir()])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Experiments", total_experiments)
    c2.metric("Analyses", sum(analysis_counts.values()))
    c3.metric("Publication Figures", figure_count)
    c4.metric("Project Version", "v1.0")

    st.write("### Analysis summary")
    st.dataframe(
        pd.DataFrame([{"Method": k, "Completed analyses": v} for k, v in analysis_counts.items()]),
        use_container_width=True
    )

    st.write("### Latest generated figures")
    recent_pngs = []
    for exp_name in experiments:
        fig_root = Path(project_path) / "Experiments" / exp_name / "Figures"
        if fig_root.exists():
            recent_pngs.extend(fig_root.rglob("*.png"))

    recent_pngs = sorted(recent_pngs, key=lambda p: p.stat().st_mtime, reverse=True)[:6]

    if recent_pngs:
        cols = st.columns(3)
        for i, p in enumerate(recent_pngs):
            with cols[i % 3]:
                st.image(str(p), caption=p.name, use_container_width=True)
    else:
        st.info("아직 생성된 figure가 없습니다.")

    st.write("### Project backup")
    if st.button("Create Project Backup", key="backup_project"):
        backup_path = create_project_backup(project_path)
        st.success("Project backup created.")
        st.code(str(backup_path))

if selected_page == "Experiments":
    st.subheader("New Experiment")
    col1, col2 = st.columns(2)
    with col1:
        exp_name = st.text_input("Experiment name", value=f"Experiment_{len(project_info['experiments'])+1:03d}")
        researcher = st.text_input("Researcher", value="")
        sensor = st.text_input("Sensor / Electrode", value="Carbon SPE")
        recognition = st.text_input("Recognition element", value="Aptamer")
        target = st.text_input("Target", value="RNA")
    with col2:
        temperature = st.text_input("Temperature", value="75 °C")
        reaction_time = st.text_input("Reaction time", value="10 min")
        electrolyte = st.text_input("Electrolyte", value="5 mM Fe(CN)6 in 0.1 M KCl")
        technique = st.multiselect("Techniques", ["DPV", "SWV", "EIS", "CV"], default=["DPV", "SWV", "EIS"])
        comment = st.text_area("Comment", value="")

    if st.button("Create Experiment"):
        exp_info = {
            "experiment_name": exp_name, "researcher": researcher, "sensor": sensor,
            "recognition": recognition, "target": target, "temperature": temperature,
            "reaction_time": reaction_time, "electrolyte": electrolyte, "technique": technique,
            "comment": comment, "raw_files": [], "results": [], "publication_figures": []
        }
        exp_path = create_experiment(project_path, project_info, exp_info)
        st.success(f"Experiment created: {exp_name}")
        st.code(str(exp_path))
        st.rerun()

    st.divider()
    experiments = project_info.get("experiments", [])
    if experiments:
        selected_exp = st.selectbox("Select experiment", experiments)
        exp_json = Path(project_path) / "Experiments" / selected_exp / "experiment.json"
        st.json(load_json(exp_json))
    else:
        st.info("아직 실험이 없습니다.")


if selected_page == "Experiment Wizard":
    st.subheader("Experiment Wizard")

    sensor_names = get_names(project_path, "sensors")
    sample_names = get_names(project_path, "samples")
    recognition_names = get_names(project_path, "recognition_elements")
    reagent_names = get_names(project_path, "reagents")

    if not sensor_names or not sample_names or not recognition_names or not reagent_names:
        seed_default_database(project_path)
        sensor_names = get_names(project_path, "sensors")
        sample_names = get_names(project_path, "samples")
        recognition_names = get_names(project_path, "recognition_elements")
        reagent_names = get_names(project_path, "reagents")

    col1, col2 = st.columns(2)

    with col1:
        wizard_exp_name = st.text_input("New experiment name", value=f"Experiment_{len(project_info['experiments'])+1:03d}", key="wizard_exp_name")
        wizard_researcher = st.text_input("Researcher", value="", key="wizard_researcher")
        wizard_sensor = st.selectbox("Sensor", sensor_names, key="wizard_sensor")
        wizard_sample = st.selectbox("Target / Sample", sample_names, key="wizard_sample")
        wizard_recognition = st.selectbox("Recognition element", recognition_names, key="wizard_recognition")

    with col2:
        wizard_reagent = st.selectbox("Electrolyte / Reagent", reagent_names, key="wizard_reagent")
        wizard_temperature = st.text_input("Temperature", value="75 °C", key="wizard_temperature")
        wizard_reaction_time = st.text_input("Reaction time", value="10 min", key="wizard_reaction_time")
        wizard_technique = st.multiselect("Techniques", ["DPV", "SWV", "EIS", "CV"], default=["DPV", "SWV", "EIS"], key="wizard_technique")
        wizard_comment = st.text_area("Comment", value="", key="wizard_comment")

    if st.button("Create Experiment from Wizard", type="primary"):
        exp_info = {
            "experiment_name": wizard_exp_name,
            "researcher": wizard_researcher,
            "sensor": wizard_sensor,
            "recognition": wizard_recognition,
            "target": wizard_sample,
            "temperature": wizard_temperature,
            "reaction_time": wizard_reaction_time,
            "electrolyte": wizard_reagent,
            "technique": wizard_technique,
            "comment": wizard_comment,
            "raw_files": [],
            "results": [],
            "publication_figures": []
        }

        exp_path = create_experiment(project_path, project_info, exp_info)
        st.success(f"Experiment created from wizard: {wizard_exp_name}")
        st.code(str(exp_path))
        st.rerun()

if selected_page == "Database":
    st.subheader("Research Database")

    db_tabs = st.tabs(["Sensors", "Samples", "Recognition", "Reagents"])

    with db_tabs[0]:
        st.write("### Add sensor")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Sensor name", value="Carbon SPE", key="sensor_name")
            electrode_type = st.text_input("Electrode type", value="Screen-printed electrode", key="sensor_type")
        with c2:
            material = st.text_input("Material", value="Carbon", key="sensor_material")
            manufacturer = st.text_input("Manufacturer", value="", key="sensor_maker")
        note = st.text_area("Sensor note", value="", key="sensor_note")
        if st.button("Save Sensor"):
            add_record(project_path, "sensors", {
                "name": name,
                "electrode_type": electrode_type,
                "material": material,
                "manufacturer": manufacturer,
                "note": note
            })
            st.success("Sensor saved.")
            st.rerun()
        st.dataframe(pd.DataFrame(get_table(project_path, "sensors")), use_container_width=True)

    with db_tabs[1]:
        st.write("### Add sample / target")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Sample name", value="RNA target", key="sample_name")
            target_type = st.text_input("Target type", value="RNA", key="sample_type")
        with c2:
            supplier = st.text_input("Supplier", value="", key="sample_supplier")
            lot = st.text_input("Lot", value="", key="sample_lot")
        sequence = st.text_area("Sequence", value="", key="sample_sequence")
        note = st.text_area("Sample note", value="", key="sample_note")
        if st.button("Save Sample"):
            add_record(project_path, "samples", {
                "name": name,
                "target_type": target_type,
                "sequence": sequence,
                "supplier": supplier,
                "lot": lot,
                "note": note
            })
            st.success("Sample saved.")
            st.rerun()
        st.dataframe(pd.DataFrame(get_table(project_path, "samples")), use_container_width=True)

    with db_tabs[2]:
        st.write("### Add recognition element")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Recognition name", value="Aptamer", key="rec_name")
            element_type = st.text_input("Element type", value="Aptamer", key="rec_type")
        with c2:
            modification = st.text_input("Modification", value="", key="rec_mod")
            supplier = st.text_input("Supplier", value="", key="rec_supplier")
        sequence = st.text_area("Sequence", value="", key="rec_sequence")
        note = st.text_area("Recognition note", value="", key="rec_note")
        if st.button("Save Recognition"):
            add_record(project_path, "recognition_elements", {
                "name": name,
                "element_type": element_type,
                "sequence": sequence,
                "modification": modification,
                "supplier": supplier,
                "note": note
            })
            st.success("Recognition element saved.")
            st.rerun()
        st.dataframe(pd.DataFrame(get_table(project_path, "recognition_elements")), use_container_width=True)

    with db_tabs[3]:
        st.write("### Add reagent / electrolyte")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Reagent name", value="Fe(CN)6 / KCl", key="reagent_name")
            reagent_type = st.text_input("Reagent type", value="Redox probe", key="reagent_type")
        with c2:
            concentration = st.text_input("Concentration", value="5 mM / 0.1 M", key="reagent_conc")
            pH = st.text_input("pH", value="", key="reagent_ph")
        composition = st.text_area("Composition", value="5 mM Fe(CN)6 in 0.1 M KCl", key="reagent_comp")
        note = st.text_area("Reagent note", value="", key="reagent_note")
        if st.button("Save Reagent"):
            add_record(project_path, "reagents", {
                "name": name,
                "reagent_type": reagent_type,
                "composition": composition,
                "concentration": concentration,
                "pH": pH,
                "note": note
            })
            st.success("Reagent saved.")
            st.rerun()
        st.dataframe(pd.DataFrame(get_table(project_path, "reagents")), use_container_width=True)


if selected_page == "Raw Data Import":
    st.subheader("Import instrument raw files into experiment")
    experiments = project_info.get("experiments", [])
    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_import = st.selectbox("Experiment", experiments, key="import_exp")
        data_type = st.selectbox("Data type", ["DPV", "SWV", "EIS", "CV"])
        import_type_map = {
            "DPV": ["mtd", "csv"],
            "SWV": ["mts", "csv"],
            "EIS": ["mteisp", "csv"],
            "CV": ["csv"],
        }
        uploaded_files = st.file_uploader(
            "Upload instrument raw files or CSV files",
            type=import_type_map[data_type],
            accept_multiple_files=True,
        )
        if st.button("Import files"):
            exp_path = Path(project_path) / "Experiments" / selected_exp_import
            raw_dir = exp_path / "RawData" / data_type
            raw_dir.mkdir(parents=True, exist_ok=True)
            exp_json = exp_path / "experiment.json"
            exp_info = load_json(exp_json)
            imported = []
            for file in uploaded_files:
                save_path = raw_dir / file.name
                with open(save_path, "wb") as f:
                    f.write(file.getbuffer())
                imported.append({
                    "file": file.name, "data_type": data_type,
                    "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "relative_path": str(Path("RawData") / data_type / file.name)
                })
            exp_info["raw_files"].extend(imported)
            save_json(exp_json, exp_info)
            st.success(f"{len(imported)} files imported.")
            st.dataframe(pd.DataFrame(imported), use_container_width=True)

def analysis_tab(method, parse_func, run_func, key_prefix):
    st.subheader(f"Run {method} analysis")
    experiments = project_info.get("experiments", [])
    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
        return
    selected_exp = st.selectbox("Experiment", experiments, key=f"{key_prefix}_exp")
    exp_path = Path(project_path) / "Experiments" / selected_exp
    raw_dir = exp_path / "RawData" / method
    if not raw_dir.exists():
        st.warning(f"이 experiment에는 {method} RawData 폴더가 없습니다. 먼저 Raw Data Import를 해줘.")
        return
    csv_files = sorted([p.name for p in raw_dir.glob("*.csv")])
    if not csv_files:
        st.warning(f"{method} CSV 파일이 없습니다.")
        return
    rows = []
    for fname in csv_files:
        label, conc_pm = parse_func(fname)
        rows.append({"File": fname, "Label": label, "Concentration_pM": 0.0 if conc_pm is None else conc_pm})
    edited_df = st.data_editor(pd.DataFrame(rows), use_container_width=True, num_rows="dynamic", key=f"{key_prefix}_table")
    use_abs_fit = st.checkbox("Use absolute value for fitting", value=True, key=f"{key_prefix}_abs")

    run_kwargs = {"use_abs_fit": use_abs_fit}

    if method == "DPV":
        st.write("#### DPV peak and baseline detection")
        baseline_mode_label = st.selectbox(
            "Baseline detection",
            [
                "Shape-based: local minimum before main peak",
                "Legacy: fixed potential region ≤ 0 V",
            ],
            index=0,
            key="dpv_baseline_mode",
        )

        if baseline_mode_label.startswith("Shape-based"):
            c1, c2, c3 = st.columns(3)
            peak_search_min_v = c1.number_input(
                "Peak search start (V)",
                value=0.30,
                step=0.01,
                format="%.3f",
                key="dpv_peak_search_min",
            )
            peak_search_max_v = c2.number_input(
                "Peak search end (V)",
                value=0.70,
                step=0.01,
                format="%.3f",
                key="dpv_peak_search_max",
            )
            baseline_search_min_v = c3.number_input(
                "Minimum search start (V)",
                value=0.05,
                step=0.01,
                format="%.3f",
                key="dpv_baseline_search_min",
            )

            smoothing_window = st.number_input(
                "Detection smoothing window (odd points; raw current is not smoothed)",
                min_value=5,
                max_value=101,
                value=11,
                step=2,
                key="dpv_smoothing_window",
            )

            run_kwargs.update({
                "baseline_mode": "preceding_local_minimum",
                "peak_search_min_v": float(peak_search_min_v),
                "peak_search_max_v": float(peak_search_max_v),
                "baseline_search_min_v": float(baseline_search_min_v),
                "smoothing_window": int(smoothing_window),
            })
        else:
            run_kwargs["baseline_mode"] = "fixed_region"

    if st.button(f"Run {method} Analysis", type="primary", key=f"{key_prefix}_run"):
        try:
            with st.spinner(f"Running {method} analysis..."):
                result = run_func(exp_path, edited_df, **run_kwargs)
            exp_json = exp_path / "experiment.json"
            exp_info = load_json(exp_json)
            exp_info["results"].append({
                "analysis": method, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result_dir": result["result_dir"], "figure_dir": result["figure_dir"], "report_dir": result["report_dir"]
            })
            save_json(exp_json, exp_info)
            st.success(f"{method} analysis complete.")
            if method == "EIS":
                st.write("Rct values"); st.dataframe(result["rct_df"], use_container_width=True)
            else:
                st.write("Peak values"); st.dataframe(result["peak_df"], use_container_width=True)
            st.write("Fit summary"); st.dataframe(result["fit_summary_df"], use_container_width=True)
            st.code(result["figure_dir"])
        except Exception as e:
            st.error(f"{method} analysis failed: {e}")

if selected_page == "DPV Analysis":
    analysis_tab("DPV", parse_dpv_concentration, run_dpv_analysis, "dpv")
if selected_page == "SWV Analysis":
    analysis_tab("SWV", parse_swv_concentration, run_swv_analysis, "swv")
if selected_page == "EIS Analysis":
    analysis_tab("EIS", parse_eis_concentration, run_eis_analysis, "eis")



if selected_page == "CV Analysis":
    st.subheader("CV Analysis")

    experiments = project_info.get("experiments", [])
    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_cv = st.selectbox("Experiment", experiments, key="cv_exp")
        exp_path = Path(project_path) / "Experiments" / selected_exp_cv
        raw_dir = exp_path / "RawData" / "CV"

        if not raw_dir.exists():
            st.warning("이 experiment에는 CV RawData 폴더가 없습니다. 먼저 Raw Data Import에서 CV 파일을 업로드해줘.")
        else:
            csv_files = sorted([p.name for p in raw_dir.glob("*.csv")])

            if not csv_files:
                st.warning("CV CSV 파일이 없습니다.")
            else:
                rows = []
                for fname in csv_files:
                    scan_rate = parse_scan_rate(fname)
                    rows.append({
                        "File": fname,
                        "Label": fname.replace(".csv", ""),
                        "ScanRate_mV_s": "" if scan_rate is None else scan_rate
                    })

                sample_df = pd.DataFrame(rows)
                st.write("CV sample information")
                edited_cv_df = st.data_editor(sample_df, use_container_width=True, num_rows="dynamic", key="cv_table")

                if st.button("Run CV Analysis", type="primary", key="cv_run"):
                    try:
                        with st.spinner("Running CV analysis..."):
                            result = run_cv_analysis(exp_path, edited_cv_df)

                        exp_json = exp_path / "experiment.json"
                        exp_info = load_json(exp_json)
                        exp_info["results"].append({
                            "analysis": "CV",
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result_dir": result["result_dir"],
                            "figure_dir": result["figure_dir"],
                            "report_dir": result["report_dir"]
                        })
                        save_json(exp_json, exp_info)

                        st.success("CV analysis complete.")

                        st.write("CV peak values")
                        st.dataframe(result["cv_df"], use_container_width=True)

                        if not result["scan_summary_df"].empty:
                            st.write("Scan-rate summary")
                            st.dataframe(result["scan_summary_df"], use_container_width=True)

                        st.write("Output folders")
                        st.code(result["result_dir"])
                        st.code(result["figure_dir"])
                        st.code(result["report_dir"])

                    except Exception as e:
                        st.error(f"CV analysis failed: {e}")


if selected_page == "Statistics":
    st.subheader("Statistics Engine")

    experiments = project_info.get("experiments", [])
    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_stats = st.selectbox("Experiment", experiments, key="stats_exp")
        method_stats = st.selectbox("Analysis type", ["DPV", "SWV", "EIS", "CV"], key="stats_method")

        exp_path = Path(project_path) / "Experiments" / selected_exp_stats
        result_dir = exp_path / "Results" / method_stats

        candidate_files = []
        if result_dir.exists():
            candidate_files.extend([p for p in result_dir.rglob("*.csv") if p.is_file()])
            candidate_files.extend([p for p in result_dir.rglob("*.xlsx") if p.is_file()])

        input_mode = st.radio("Input mode", ["Use existing result file", "Upload statistics table"], key="stats_input_mode")
        selected_input_path = None

        if input_mode == "Use existing result file":
            if not candidate_files:
                st.warning("해당 analysis 결과 파일이 없습니다. 먼저 DPV/SWV/EIS 분석을 실행하거나 파일을 업로드해줘.")
            else:
                candidate_labels = [str(p.relative_to(result_dir)) for p in candidate_files]
                selected_label = st.selectbox("Result file", candidate_labels, key="stats_file")
                selected_input_path = candidate_files[candidate_labels.index(selected_label)]
                st.code(str(selected_input_path))
        else:
            uploaded_stat_file = st.file_uploader("Upload CSV or Excel file for statistics", type=["csv", "xlsx"], key="stats_upload")
            if uploaded_stat_file is not None:
                stats_input_dir = exp_path / "Results" / method_stats / "Statistics" / "Input"
                stats_input_dir.mkdir(parents=True, exist_ok=True)
                selected_input_path = stats_input_dir / uploaded_stat_file.name
                with open(selected_input_path, "wb") as f:
                    f.write(uploaded_stat_file.getbuffer())
                st.code(str(selected_input_path))

        signal_column = st.text_input("Signal column name (optional)", value="", help="비워두면 DeltaDeltaPeak, Rct 등 주요 컬럼을 자동으로 찾습니다.", key="stats_signal_col")
        signal_column = signal_column.strip() or None

        error_bar = st.selectbox("Error bar", ["SD", "SEM", "CI95"], key="stats_errorbar")
        lod_error_source = st.selectbox("LOD/LOQ sigma source", ["SD", "SEM"], key="stats_lod_sigma")

        if st.button("Run Statistics", type="primary", key="stats_run"):
            if selected_input_path is None:
                st.error("Statistics input file이 필요합니다.")
            else:
                try:
                    result = run_statistics_analysis(
                        exp_path=exp_path,
                        method=method_stats,
                        input_file=selected_input_path,
                        signal_column=signal_column,
                        error_bar=error_bar,
                        lod_error_source=lod_error_source,
                    )

                    st.success("Statistics analysis complete.")
                    st.write("Replicate values")
                    st.dataframe(result["replicate_df"], use_container_width=True)
                    st.write("Statistics summary")
                    st.dataframe(result["summary_df"], use_container_width=True)
                    st.write("LOD / LOQ")
                    st.dataframe(pd.DataFrame([result["lod_info"]]), use_container_width=True)
                    st.write("Output folders")
                    st.code(result["result_dir"])
                    st.code(result["figure_dir"])
                    st.code(result["report_dir"])

                except Exception as e:
                    st.error(f"Statistics analysis failed: {e}")


if selected_page == "Figure Builder":
    st.subheader("Figure Builder")

    if PPTX_AVAILABLE:
        st.success("PowerPoint export is available.")
    else:
        st.warning("PowerPoint export is unavailable. Install `python-pptx` to enable PPTX export. PNG/SVG/Caption still work.")

    experiments = project_info.get("experiments", [])
    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_fig = st.selectbox("Experiment", experiments, key="fig_exp")
        exp_path = Path(project_path) / "Experiments" / selected_exp_fig
        available = collect_figure_files(exp_path)

        if not available:
            st.warning("아직 생성된 figure가 없습니다. 먼저 DPV/SWV/EIS 분석을 실행해줘.")
        else:
            labels = [x["label"] for x in available]
            selected_labels = st.multiselect("Select up to 4 figures", labels, default=labels[:4])
            figure_name = st.text_input("Figure name", value=suggest_next_figure_name(exp_path))
            layout = st.selectbox("Layout", ["auto", "2x2", "1x3"])
            make_pptx = st.checkbox("Export PowerPoint (.pptx)", value=PPTX_AVAILABLE, disabled=not PPTX_AVAILABLE)

            path_map = {x["label"]: x["path"] for x in available}

            if st.button("Generate Composite Figure", type="primary"):
                selected_paths = [path_map[l] for l in selected_labels]

                try:
                    result = make_composite_figure(
                        exp_path,
                        selected_paths,
                        figure_name=figure_name,
                        layout=layout,
                        make_pptx=make_pptx
                    )

                    exp_json = exp_path / "experiment.json"
                    exp_info = load_json(exp_json)
                    exp_info.setdefault("publication_figures", [])
                    exp_info["publication_figures"].append({
                        "figure_name": figure_name,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "output_dir": result["output_dir"],
                        "png": result["png"],
                        "svg": result["svg"],
                        "pptx": result["pptx"],
                        "caption_path": result["caption_path"]
                    })
                    save_json(exp_json, exp_info)

                    st.success("Composite figure generated.")
                    st.info(result["pptx_message"])
                    st.image(result["png"])

                    st.write("Caption")
                    st.text(result["caption"])

                    st.write("Used files")
                    st.dataframe(result["used_files"], use_container_width=True)

                    st.write("Output folder")
                    st.code(result["output_dir"])

                except Exception as e:
                    st.error(f"Figure generation failed: {e}")


if selected_page == "ELN":
    st.subheader("Electronic Lab Notebook")
    experiments = project_info.get("experiments", [])

    if not experiments:
        st.info("먼저 Experiment를 만들어줘.")
    else:
        selected_exp_eln = st.selectbox("Experiment", experiments, key="eln_exp")
        exp_path = Path(project_path) / "Experiments" / selected_exp_eln
        exp_json = exp_path / "experiment.json"
        exp_info = load_json(exp_json) if exp_json.exists() else {}

        form_tab, history_tab = st.tabs(["New entry", "Notebook history"])

        with form_tab:
            c1, c2 = st.columns(2)
            with c1:
                title = st.text_input("Entry title", value=f"{selected_exp_eln} experiment note", key="eln_title")
                researcher = st.text_input("Researcher", value=exp_info.get("researcher",""), key="eln_researcher")
                category = st.selectbox("Category", ["Experiment","Sample preparation","Surface modification","Measurement","Analysis","Troubleshooting","Other"], key="eln_category")
                electrode = st.text_input("Electrode / Sensor", value=exp_info.get("sensor",""), key="eln_electrode")
                recognition = st.text_input("Recognition element", value=exp_info.get("recognition",""), key="eln_recognition")
            with c2:
                target = st.text_input("Target / Sample", value=exp_info.get("target",""), key="eln_target")
                surface = st.text_input("Surface modification", value="", key="eln_surface")
                measurement = st.multiselect("Measurement", ["DPV","SWV","EIS","CV","Other"], default=exp_info.get("technique",[]), key="eln_measurement")
                temperature = st.text_input("Temperature", value=exp_info.get("temperature",""), key="eln_temperature")
                reaction_time = st.text_input("Reaction time", value=exp_info.get("reaction_time",""), key="eln_reaction_time")

            protocol = st.text_area("Protocol / Procedure", height=150, key="eln_protocol")
            observation = st.text_area("Observation", height=120, key="eln_observation")
            result_summary = st.text_area("Result summary", height=120, key="eln_result")
            next_action = st.text_area("Next action", height=90, key="eln_next")
            files = st.file_uploader("Attach images or documents", type=["png","jpg","jpeg","webp","pdf","csv","xlsx","txt"], accept_multiple_files=True, key="eln_files")

            if st.button("Save ELN Entry", type="primary", key="eln_save"):
                item = add_entry(exp_path, {
                    "title": title,
                    "researcher": researcher,
                    "category": category,
                    "electrode": electrode,
                    "surface_modification": surface,
                    "recognition_element": recognition,
                    "target": target,
                    "measurement": ", ".join(measurement),
                    "temperature": temperature,
                    "reaction_time": reaction_time,
                    "protocol": protocol,
                    "observation": observation,
                    "result_summary": result_summary,
                    "next_action": next_action
                }, uploaded_files=files)
                st.success("ELN entry saved.")
                st.code(item["entry_id"])

        with history_tab:
            entries = load_entries(exp_path)
            if not entries:
                st.info("저장된 ELN entry가 없습니다.")
            else:
                st.dataframe(entries_dataframe(entries), use_container_width=True)
                selected_id = st.selectbox(
                    "Open entry",
                    [e["entry_id"] for e in reversed(entries)],
                    format_func=lambda x: next(f"{e.get('created_at','')} | {e.get('title','')}" for e in entries if e.get("entry_id")==x),
                    key="eln_open"
                )
                e = next(x for x in entries if x.get("entry_id")==selected_id)
                st.write(f"### {e.get('title','')}")
                st.write(f"**Date:** {e.get('created_at','')}")
                st.write(f"**Researcher:** {e.get('researcher','')}")
                st.write(f"**Category:** {e.get('category','')}")
                st.write(f"**Electrode:** {e.get('electrode','')}")
                st.write(f"**Surface modification:** {e.get('surface_modification','')}")
                st.write(f"**Recognition element:** {e.get('recognition_element','')}")
                st.write(f"**Target:** {e.get('target','')}")
                st.write(f"**Measurement:** {e.get('measurement','')}")
                st.write("#### Protocol / Procedure")
                st.write(e.get("protocol",""))
                st.write("#### Observation")
                st.write(e.get("observation",""))
                st.write("#### Result summary")
                st.write(e.get("result_summary",""))
                st.write("#### Next action")
                st.write(e.get("next_action",""))

                for a in e.get("attachments",[]):
                    ap = exp_path / a["relative_path"]
                    if ap.suffix.lower() in [".png",".jpg",".jpeg",".webp"]:
                        st.image(str(ap), caption=a["name"], width=420)
                    elif ap.exists():
                        with open(ap,"rb") as f:
                            st.download_button(f"Download {a['name']}", data=f.read(), file_name=a["name"], key=f"dl_{selected_id}_{a['name']}")

                md = export_markdown(exp_path, entries)
                with open(md,"rb") as f:
                    st.download_button("Download ELN as Markdown", data=f.read(), file_name=f"{selected_exp_eln}_ELN.md", key="eln_md")

                confirm = st.checkbox("I understand this will delete the selected entry", key="eln_confirm_delete")
                if st.button("Delete selected entry", disabled=not confirm, key="eln_delete"):
                    delete_entry(exp_path, selected_id)
                    st.success("Entry deleted.")
                    st.rerun()


if selected_page == "Project Info":
    st.subheader("Project JSON")
    st.json(project_info)
    st.write("Project folder:")
    st.code(str(project_path))
