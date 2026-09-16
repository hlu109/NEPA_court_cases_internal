/*==============================================================================
	This script analyzes the NEPA cases. 
==============================================================================*/
* packages (uncomment once as needed)
// ssc install ivreg2, replace
// ssc install ranktest, replace // required for ivreg2

set graphics off
// set graphics on

* Set user
global user = c(username)
if "$user" == "agupta011" {
    global dropbox "/Users/agupta011/Dropbox/NEPA_court_cases"
}
else if "$user" == "hl2266" {
    local cwd = lower("`c(pwd)'")
    if strpos("`cwd'", "dropbox") {
        global dropbox "C:/Users/hl2266/YLS Dropbox/Hannah Lu/shared/NEPA Court Cases (Internal)"
        global code_dir "${dropbox}/Code/NEPA_court_cases_internal"
    }
    else if strpos("`cwd'", "docker") {
        global dropbox "C:/Users/hl2266/YLS Dropbox/Hannah Lu/shared/NEPA Court Cases (Internal)"
        global code_dir "C:/Users/hl2266/project_dockers/nepa/Code/NEPA_court_cases_internal"
    }
    else if strpos("`cwd'", "pi_zdl3") {
        global dropbox "/nfs/roberts/project/pi_zdl3/shared/NEPA court case project"
        global code_dir "${dropbox}/Code/NEPA_court_cases_internal"
    }
    else {
        display as error "Hannah - error setting directories"
    }
    global overleaf_dir "C:/Users/hl2266/project_dockers/nepa/Overleaf/NEPA Court Cases Overleaf"
    global overleaf_tabdir "${overleaf_dir}/Tables"
    global overleaf_figdir "${overleaf_dir}/Figures"
    cap mkdir "$overleaf_tabdir"
    cap mkdir "$overleaf_figdir"
}
* add your username and paths here as an else if condition
else {
    display as error "Set your user"
}

global data_dir "${dropbox}/Data"
global output_dir "${dropbox}/Outputs"
global tabdir "${output_dir}/Tables"
global figdir "${output_dir}/Figures"

cap mkdir "$output_dir"
cap mkdir "$tabdir"
cap mkdir "$figdir"

* ==============================================================================
* helper function to streamline with overleaf 
cap program drop copy_tab_to_overleaf
program define copy_tab_to_overleaf
	args fname
	if "$user" == "hl2266" {
		copy "$tabdir/`fname'" "$overleaf_tabdir/`fname'", replace
	}
end
cap program drop copy_fig_to_overleaf
program define copy_fig_to_overleaf
	args fname
	if "$user" == "hl2266" {
		copy "$figdir/`fname'" "$overleaf_figdir/`fname'", replace
	}
end

* ==============================================================================
* gates to toggle on/off different sections of this script 
global prelim_analysis = 0
global judgeIV_stage1 = 0
global judgeIV_stage2 = 1
global judgeIV_6yr = 1
* ==============================================================================

* ------------------------------------------------------------------
* Load + clean case-level data
* ------------------------------------------------------------------
if $prelim_analysis == 1 | $judgeIV_stage1 == 1 | $judgeIV_stage2 == 1 | $judgeIV_6yr == 1 {

    insheet using "${data_dir}/Intermediate/Feature Classification Predictions/courtlistener_metadata_w_extracted_features.csv", clear

    * track number of cases before and after duplicate cleaning
    count
    local n_raw = r(N)

    * Collapse duplicate opinions
    * TODO: move this upstream into 05_clean_merge_split_cases.py
    keep lead_opinion_id cluster_id court court_id datefiled year_filed casename docket_numbers_parsed docket_no1 docket_no2 docket_no3 docket_no4 docket_no5 citation source file_source_indicator ///
        district_outcome disposition prevailing_party district_score disposition_score prevailing_score pro_dev_district_score pro_dev_prevailing_score ///
        panel_judges panel_judge_count opinion_authors opinion_author_count en_banc per_curiam panel_judge_1 panel_judge_2 panel_judge_3 author_judge_1 author_judge_2 author_judge_3

    * handle duplicates in court + exact cleaned docket match + date opinion filed match
    * rows without a parsed docket get their own key so they are never merged
    gen dk = docket_numbers_parsed
    replace dk = "nodk_" + string(cluster_id, "%12.0f") if mi(dk)

    * rank of opinion versions: prefer if gemini used both pdf and html; then prefer if reporter citation is available; then prefer if CourtListener already merged from multiple sources upstream; tiebreaker by larger cluster id number
    gen byte is_pdf = (file_source_indicator == "html+pdf")
    gen byte mi_cite = mi(citation)
    gen n_src = strlen(source)
    gsort court_id dk datefiled -is_pdf mi_cite -n_src -cluster_id, generate(sort_order)
    bysort court_id dk datefiled (sort_order): gen copy_rank = _n
    * track duplicates and their cluster ids
    by court_id dk datefiled: gen n_dup_copies = _N
    by court_id dk datefiled: gen dup_cluster_ids = string(cluster_id, "%12.0f") if _n == 1
    by court_id dk datefiled: replace dup_cluster_ids = dup_cluster_ids[_n-1] + ";" + string(cluster_id, "%12.0f") if _n > 1
    by court_id dk datefiled: replace dup_cluster_ids = dup_cluster_ids[_N]

    keep if copy_rank == 1 // TODO: later we can fill in outcomes that may be populated in some copies but not others. and also address conflicts in the gemini coding
    drop copy_rank dk sort_order
    tab n_dup_copies

    * handle duplicates in court + exact case name + date opinion filed match
    * rows without a case name get their own key so they are never merged
    gen cn = lower(strtrim(itrim(casename)))
    replace cn = "nocn_" + string(cluster_id, "%12.0f") if mi(cn)

    * rank of opinion versions: prefer if gemini used both pdf and html; then prefer if reporter citation is available; then prefer if CourtListener already merged from multiple sources upstream; tiebreaker by larger cluster id number
    gsort court_id cn datefiled -is_pdf mi_cite -n_src -cluster_id, generate(sort_order)
    bysort court_id cn datefiled (sort_order): gen copy_rank = _n
    * track duplicates and their cluster ids, adding to the counts and id lists from the docket pass
    by court_id cn datefiled: egen n_copies_grp = total(n_dup_copies)
    by court_id cn datefiled: gen ids_grp = dup_cluster_ids if _n == 1
    by court_id cn datefiled: replace ids_grp = ids_grp[_n-1] + ";" + dup_cluster_ids if _n > 1
    by court_id cn datefiled: replace ids_grp = ids_grp[_N]
    replace n_dup_copies = n_copies_grp
    replace dup_cluster_ids = ids_grp

    keep if copy_rank == 1 // TODO: later we can fill in outcomes that may be populated in some copies but not others. and also address conflicts in the gemini coding
    drop copy_rank cn sort_order n_copies_grp ids_grp
    tab n_dup_copies

    * handle duplicates in court + just first docket number + date opinion filed match
    * TODO: later we prob want to match on any partial set overlap of docket numbers. Claude identified around 40 here, so not a huge priority, but we'd probably need some further cleaning of docket numbers first 
    * rows without a first docket number get their own key so they are never merged
    gen dk1 = docket_no1
    replace dk1 = "nodk1_" + string(cluster_id, "%12.0f") if mi(dk1)

    * rank of opinion versions: prefer if gemini used both pdf and html; then prefer if reporter citation is available; then prefer if CourtListener already merged from multiple sources upstream; tiebreaker by larger cluster id number
    gsort court_id dk1 datefiled -is_pdf mi_cite -n_src -cluster_id, generate(sort_order)
    bysort court_id dk1 datefiled (sort_order): gen copy_rank = _n
    * track duplicates and their cluster ids, adding to the counts and id lists from the above passes
    by court_id dk1 datefiled: egen n_copies_grp = total(n_dup_copies)
    by court_id dk1 datefiled: gen ids_grp = dup_cluster_ids if _n == 1
    by court_id dk1 datefiled: replace ids_grp = ids_grp[_n-1] + ";" + dup_cluster_ids if _n > 1
    by court_id dk1 datefiled: replace ids_grp = ids_grp[_N]
    replace n_dup_copies = n_copies_grp
    replace dup_cluster_ids = ids_grp


    keep if copy_rank == 1 // TODO: later we can fill in outcomes that may be populated in some copies but not others. and also address conflicts in the gemini coding
    drop copy_rank dk1 is_pdf mi_cite n_src sort_order n_copies_grp ids_grp
    tab n_dup_copies

    * track number of cases before and after duplicate cleaning
    count
    display "Duplicate cleaning: `n_raw' rows in, " r(N) " rows out, " `n_raw' - r(N) " duplicate copies dropped (" %4.1f 100 * (`n_raw' - r(N)) / `n_raw' "% of rows)"

    gen int year = year_filed // (time of opinion decision)

    * check duplicate opinions
    duplicates tag court_id docket_numbers_parsed datefiled, generate(dup_cdd)
    duplicates tag court_id casename datefiled, generate(dup_cnd)
    duplicates tag court_id docket_no1 datefiled, generate(dup_cd1d)
    duplicates tag court_id docket_numbers_parsed, generate(dup_cd)
    duplicates tag court_id casename, generate(dup_cn)
    duplicates tag court_id docket_no1, generate(dup_cd1)

    order lead_opinion_id dup_cd dup_cn dup_cd1 datefiled docket_numbers_parsed casename court_id district_outcome disposition prevailing_party district_score disposition_score prevailing_score panel_judge_count panel_judge_1 panel_judge_2 panel_judge_3 file_source_indicator source citation
    char casename[_de_col_width_] 50
    char docket_numbers_parsed[_de_col_width_] 50
    // count if dup_cdd == 0 & dup_cnd == 0 & dup_cd == 0 & dup_cn == 0
    // drop if dup_cdd == 0
    // gsort -dup_cdd datefiled

    // drop if dup_cn == 0 & dup_cd == 0
    gsort -dup_cd1 -dup_cd -dup_cn docket_numbers_parsed -datefiled
    // count if dup_cn != 0 & dup_cd == 0
    // exit


    * Clean spacing first
    gen strL casename_clean = strtrim(itrim(casename))

    * Create output vars
    gen strL party1 = ""
    gen strL party2 = ""

    * Split on " v. " (allow multiple spaces)
    replace party1 = strtrim(regexs(1)) if regexm(casename_clean, "^(.*)\s+v\.\s+(.*)$")
    replace party2 = strtrim(regexs(2)) if regexm(casename_clean, "^(.*)\s+v\.\s+(.*)$")

    gen one = 1
    bys party1: egen total_cases_p1 = total(one)
    bys party2: egen total_cases_p2 = total(one)


    /* A numeric variable for courts to be used in FE */
    encode court, gen(numeric_court)

    /* Some Simple Summary Stats*/
    * judge missing
    rename panel_judge_count judges_on_case
    tab judges_on_case, mi
    replace judges_on_case = 0 if mi(judges_on_case)
    tab judges_on_case, mi
    gen judge_miss = (judges_on_case == 0)
    tab judge_miss

}

* ------------------------------------------------------------------
* Preliminary analysis: party frequency summary stats and figures
* ------------------------------------------------------------------
if $prelim_analysis == 1 {

    * party identities
    tab party1 if total_cases_p1 > 10, sort
    preserve
        keep if total_cases_p1 > 10
        contract party1, freq(n_cases)
        gsort -n_cases
        local N = _N
        graph hbar n_cases, over(party1, sort(n_cases) descending label(labsize(vsmall))) ///
            ytitle("Number of Cases") ///
            title("Most Frequent Plaintiffs (>10 cases)") ///
            bar(1, color(maroon)) ///
            blabel(bar, size(vsmall) format(%9.0f)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/plaintiff_bar.png", replace width(1200)
        copy_fig_to_overleaf "plaintiff_bar.png"
    restore


    tab party2 if total_cases_p2 > 10, sort

    preserve
        keep if total_cases_p2 > 10
        contract party2, freq(n_cases)
        gsort -n_cases
        local N = _N
        graph hbar n_cases, over(party2, sort(n_cases) descending label(labsize(vsmall))) ///
            ytitle("Number of Cases") ///
            title("Most Frequent Defendants (>10 cases)") ///
            bar(1, color(maroon)) ///
            blabel(bar, size(vsmall) format(%9.0f)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/defendant_bar.png", replace width(1200)
        copy_fig_to_overleaf "defendant_bar.png"
    restore

    * plot number of cases over time

    * -- compare district outcomes
    preserve
        gen byte plaintiff = (district_outcome == "plaintiff")
        gen byte defendant = (district_outcome == "defendant")
        gen byte mixed = (district_outcome == "mixed")

        collapse (sum) n_total = one (sum) plaintiff (sum) defendant (sum) mixed, by(year)
        sort year

        twoway (line n_total year) ///
               (line plaintiff year) ///
               (line defendant year) ///
               (line mixed year), ///
            legend(order(1 "All" 2 "Plaintiff" 3 "Defendant" 4 "Mixed") rows(4) cols(1) size(vsmall) position(3) region(lstyle(none))) ///
            ytitle("Number of Cases") xtitle("Year Appellate Case Decided") ///
            xlabel(1970(10)2025) xscale(range(1970 2025)) ///
            title("NEPA Cases Over Time - District Outcomes") ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/cases_over_time_district_outcome.png", replace width(1200)
        copy_fig_to_overleaf "cases_over_time_district_outcome.png"
    restore

    * -- compare appellate outcomes
    preserve
        gen byte plaintiff = (prevailing_party == "plaintiff")
        gen byte defendant = (prevailing_party == "defendant")
        gen byte mixed = (prevailing_party == "mixed")

        collapse (sum) n_total = one (sum) plaintiff (sum) defendant (sum) mixed, by(year)
        sort year

        twoway (line n_total year) ///
               (line plaintiff year) ///
               (line defendant year) ///
               (line mixed year), ///
            legend(order(1 "All" 2 "Plaintiff" 3 "Defendant" 4 "Mixed") rows(4) size(vsmall) position(3) region(lstyle(none))) ///
            ytitle("Number of Cases") xtitle("Year Decided") ///
            xlabel(1970(10)2025) xscale(range(1970 2025)) ///
            title("NEPA Cases Over Time - Appellate Outcomes") ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/cases_over_time_prevailing_party.png", replace width(1200)
        copy_fig_to_overleaf "cases_over_time_prevailing_party.png"
    restore

    * -- compare dispositions
    preserve
        gen byte reverse = (disposition == "reverse")
        gen byte affirm = (disposition == "affirm")
        gen byte mixed = (disposition == "mixed")

        collapse (sum) n_total = one (sum) reverse (sum) affirm (sum) mixed, by(year)
        sort year

        twoway (line n_total year) ///
               (line reverse year) ///
               (line affirm year) ///
               (line mixed year), ///
            legend(order(1 "All" 2 "Reversal" 3 "Affirm" 4 "Mixed") rows(4) size(vsmall) position(3) region(lstyle(none))) ///
            ytitle("Number of Cases") xtitle("Year Decided") ///
            xlabel(1970(10)2025) xscale(range(1970 2025)) ///
            title("NEPA Cases Over Time - Dispositions") ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/cases_over_time_disposition.png", replace width(1200)
        copy_fig_to_overleaf "cases_over_time_disposition.png"
    restore

}

* ------------------------------------------------------------------
* Judge IV first stage
* ------------------------------------------------------------------
if $judgeIV_stage1 == 1 | $judgeIV_stage2 == 1 | $judgeIV_6yr == 1 {

    * ============================================================
    * Step 1: Set aside cases with no judges identified (to append back after judge processing)
    * ============================================================
    gen case_id = _n
    gen byte no_judge = judge_miss

    preserve
        keep if no_judge
        tempfile no_judge_cases
        save `no_judge_cases'
    restore
    drop if no_judge

    * ============================================================
    * Step 2: Reshape to judge-level
    * ============================================================
    reshape long panel_judge_, i(case_id) j(judge_num)
    rename panel_judge_ judge_name
    drop if missing(judge_name) | judge_name == ""

    * ============================================================
    * Step 3: Count cases per judge
    * ============================================================
    bysort judge_name: gen case_count_per_judge = _N

    * ============================================================
    * Step 4: Create binary indicator for judges with 10+ observations
    * ============================================================
    levelsof judge_name if case_count_per_judge >= 10, local(freq_judges)
    foreach j of local freq_judges {
        local vname = subinstr("`j'", " ", "_", .)
        local vname = subinstr("`vname'", ".", "", .)
        local vname = subinstr("`vname'", "'", "", .)
        gen byte d_`vname' = (judge_name == "`j'")
    }

    * ============================================================
    * Step 5: Leave-one-out judge strictness measures
    * ============================================================
    * district_score, disposition_score, and prevailing_score are computed upstream in the data and read in directly

    * --- Compute leave-one-out means relative to court average ---
    foreach var in district_score disposition_score prevailing_score {

        bysort judge_name: egen double sum_j_`var' = total(`var')
        bysort judge_name: egen long   n_j_`var'   = count(`var')
        gen double loo_judge_`var' = (sum_j_`var' - `var') / (n_j_`var' - 1) if n_j_`var' > 1

        bysort court: egen double mean_court_`var' = mean(`var')

        gen double strictness_`var' = loo_judge_`var' - mean_court_`var'

        drop sum_j_`var' n_j_`var' loo_judge_`var' mean_court_`var'
    }

    * --- Create strictness versions at two cutoffs ---
    foreach var in district_score disposition_score prevailing_score {
        gen double strictness10_`var' = strictness_`var'
        replace strictness10_`var' = . if case_count_per_judge < 10

        gen double strictness20_`var' = strictness_`var'
        replace strictness20_`var' = . if case_count_per_judge < 20
    }

    * --- Top 10 and Bottom 10 judges by prevailing party strictness ---
    preserve
        bysort judge_name: keep if _n == 1
        keep if !missing(strictness_prevailing_score) & case_count_per_judge >= 10
        keep judge_name case_count_per_judge strictness_prevailing_score
        gsort -strictness_prevailing_score
        gen rank = _n
        local N = _N

        * Top 10 plaintiff-leaning
        graph hbar strictness_prevailing_score if rank <= 10, ///
            over(judge_name, sort(strictness_prevailing_score) descending label(labsize(vsmall))) ///
            ytitle("Strictness (Prevailing Party)") ///
            title("Top 10 Most Plaintiff-Leaning Judges") ///
            bar(1, color(navy)) ///
            blabel(bar, size(vsmall) format(%5.3f)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/top10_judges.png", replace width(1200)
        copy_fig_to_overleaf "top10_judges.png"

        * Bottom 10 defendant-leaning
        graph hbar strictness_prevailing_score if rank > `N' - 10, ///
            over(judge_name, sort(strictness_prevailing_score) label(labsize(vsmall))) ///
            ytitle("Strictness (Prevailing Party)") ///
            title("Top 10 Most Defendant-Leaning Judges") ///
            bar(1, color(maroon)) ///
            blabel(bar, size(vsmall) format(%5.3f)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/bottom10_judges.png", replace width(1200)
        copy_fig_to_overleaf "bottom10_judges.png"
    restore


    eststo clear

    * --- Cutoff = 10 ---
    eststo j10_prev: reg prevailing_score  strictness10_prevailing_score i.year i.numeric_court
    eststo j10_dist: reg district_score    strictness10_district_score i.year i.numeric_court
    eststo j10_disp: reg disposition_score strictness10_disposition_score i.year i.numeric_court

    * --- Cutoff = 20 ---
    eststo j20_prev: reg prevailing_score  strictness20_prevailing_score i.year i.numeric_court
    eststo j20_dist: reg district_score    strictness20_district_score i.year i.numeric_court
    eststo j20_disp: reg disposition_score strictness20_disposition_score i.year i.numeric_court

    * --- No cutoff ---
    eststo jnc_prev: reg prevailing_score  strictness_prevailing_score i.year i.numeric_court
    eststo jnc_dist: reg district_score    strictness_district_score i.year i.numeric_court
    eststo jnc_disp: reg disposition_score strictness_disposition_score i.year i.numeric_court

    * --- No cutoff, weighted by judge caseload ---
    eststo jwt_prev: reg prevailing_score  strictness_prevailing_score   i.year i.numeric_court [aw=case_count_per_judge]
    eststo jwt_dist: reg district_score    strictness_district_score   i.year i.numeric_court [aw=case_count_per_judge]
    eststo jwt_disp: reg disposition_score strictness_disposition_score i.year i.numeric_court [aw=case_count_per_judge]

    * --- Table: Judge-level, by outcome ---
    foreach dep in prev dist disp {
        if "`dep'" == "prev" local deplab "Prevailing Party"
        if "`dep'" == "dist" local deplab "District Outcome"
        if "`dep'" == "disp" local deplab "Disposition"

        esttab j10_`dep' j20_`dep' jnc_`dep' jwt_`dep' ///
            using "${tabdir}/judge_level_`dep'.tex", replace ///
            booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
            nomtitles ///
            mgroups("10 Cutoff" "20 Cutoff" "No Cutoff" "Weighted", ///
                pattern(1 1 1 1)) ///
            indicate("Year FE = *.year" "Court FE = *.numeric_court") ///
            scalars("N Observations" "r2_a Adj. R\textsuperscript{2}") ///
            sfmt(%9.0fc %9.3f) ///
            nonumber ///
            nonotes addnotes("Standard errors in parentheses." ///
                "Weighted specification uses analytic weights equal to judge caseload." ///
                "\sym{*} \(p<0.10\), \sym{**} \(p<0.05\), \sym{***} \(p<0.01\)")
        copy_tab_to_overleaf "judge_level_`dep'.tex"
    }


    * ============================================================
    * Step 6: Roll up to case level
    * ============================================================

    * Average strictness across judges on the panel for each case
    foreach var in district_score disposition_score prevailing_score {
        bysort case_id: egen double c_strict10_`var' = mean(strictness10_`var')
        bysort case_id: egen double c_strict20_`var' = mean(strictness20_`var')
        bysort case_id: egen double c_strict_`var'   = mean(strictness_`var')
    }

    * Precision weight: minimum case_count_per_judge across panel judges
    bysort case_id: egen double min_judge_case_count = min(case_count_per_judge)

    * use judges_on_case rather than the reshaped row count, since upstream data processing truncates panels above 3 judges
    gen number_of_judges = judges_on_case

    duplicates drop case_id, force

    * Append back cases with no judge info
    append using `no_judge_cases'
    replace number_of_judges = 0 if no_judge == 1

    * drop en banc cases 
    drop if en_banc == 1

    * number of judge summaries
    tab number_of_judges
    histogram number_of_judges, discrete frequency ///
        xlabel(0(1)20) ///
        xtitle("Number of Judges on Panel") ///
        ytitle("Number of Cases") ///
        title("Distribution of Panel Size") ///
        color(navy) ///
        scheme(s2color) graphregion(color(white))
    graph export "${figdir}/panel_size_hist.png", replace width(1200)
    copy_fig_to_overleaf "panel_size_hist.png"

    * for the rest of the analysis, drop cases with more than 3 judges
    drop if number_of_judges > 3


    eststo clear

    * --- Cutoff = 10 ---
    eststo c10_prev: reg prevailing_score  c_strict10_prevailing_score i.year i.numeric_court
    eststo c10_disp: reg disposition_score c_strict10_disposition_score i.year i.numeric_court
    eststo c10_dist: reg district_score    c_strict10_district_score    i.year i.numeric_court

    * --- Cutoff = 20 ---
    eststo c20_prev: reg prevailing_score  c_strict20_prevailing_score i.year i.numeric_court
    eststo c20_disp: reg disposition_score c_strict20_disposition_score i.year i.numeric_court
    eststo c20_dist: reg district_score    c_strict20_district_score    i.year i.numeric_court

    * --- No cutoff, weighted by min panel judge caseload ---
    eststo cwt_prev: reg prevailing_score  c_strict_prevailing_score i.year i.numeric_court [aw=min_judge_case_count]
    eststo cwt_disp: reg disposition_score c_strict_disposition_score i.year i.numeric_court [aw=min_judge_case_count]
    eststo cwt_dist: reg district_score    c_strict_district_score    i.year i.numeric_court [aw=min_judge_case_count]

    * --- Table: Case-level, by outcome ---
    foreach dep in prev dist disp {
        if "`dep'" == "prev" local deplab "Prevailing Party"
        if "`dep'" == "dist" local deplab "District Outcome"
        if "`dep'" == "disp" local deplab "Disposition"

        esttab c10_`dep' c20_`dep' cwt_`dep' ///
            using "${tabdir}/case_level_`dep'.tex", replace ///
            booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
            nomtitles ///
            mgroups("10 Cutoff" "20 Cutoff" "Weighted", ///
                pattern(1 1 1)) ///
            indicate("Year FE = *.year" "Court FE = *.numeric_court") ///
            scalars("N Observations" "r2_a Adj. R\textsuperscript{2}") ///
            sfmt(%9.0fc %9.3f) ///
            nonumber ///
            nonotes addnotes("Standard errors in parentheses." ///
                "Weighted specification uses analytic weights equal to minimum judge caseload on the panel." ///
                "\sym{*} \(p<0.10\), \sym{**} \(p<0.05\), \sym{***} \(p<0.01\)")
        copy_tab_to_overleaf "case_level_`dep'.tex"
    }

    tempfile case_level
    save `case_level'

}

* ==============================================================================
* Judge IV second stage
* ==============================================================================
if $judgeIV_stage2 == 1 {
    
    use `case_level', clear

    * "adverse ruling" = NEPA gets stricter = plaintiff prevails over the agency/project defendant
    gen byte adverse_ruling = .
    replace adverse_ruling = 1 if prevailing_party == "plaintiff"
    replace adverse_ruling = 0 if prevailing_party == "defendant"

    * collapse to circuit x year
    collapse (sum) n_adverse_rulings = adverse_ruling ///
        (mean) judge_iv = c_strict_prevailing_score ///
        (count) n_cases = case_id, ///
        by(court_id court_id year)

    * fill in circuit-year observations with zero NEPA cases
    * NOTE: judge_iv stays missing since there's no judge panel to compute the strictness
    fillin court_id year
    replace n_adverse_rulings = 0 if _fillin
    replace n_cases = 0 if _fillin
    drop _fillin

    tempfile circuit_year_cases
    save `circuit_year_cases'

    * to merge highway data to appellate circuit
    import delimited "${data_dir}/Raw/state_to_circuit_crosswalk.csv", varnames(1) clear
    keep state_name court_id
    tempfile crosswalk
    save `crosswalk'

    * pull highway cost per mile and population from Brooks-Liscow
    use "${data_dir}/Raw/Brooks Liscow/Annual_In-House_Dataset.dta", clear
    keep state_name year lag_scaled_spending allMiles pop
    drop if state_name == "US_Total"
    merge m:1 state_name using `crosswalk', keep(match) nogen

    collapse (sum) lag_scaled_spending allMiles pop, by(court_id year)
    sum lag_scaled_spending
    // TODO: export sum stats to overleaf

    rename pop population // from Brooks Liscow, which was sent from Ganong and Shoag, which the past Liscow predocs assume is from the BEA 
    gen spend_per_mile = lag_scaled_spending / allMiles // defining this the same way it's constructed in the 6-yr in house data in Brooks Liscow
    tempfile circuit_year_spending
    save `circuit_year_spending'

    use `circuit_year_cases', clear
    // merge 1:1 court_id year using `circuit_year_spending', keep(match) nogen
    merge 1:1 court_id year using `circuit_year_spending'
    drop if year < 1970 | year > 1993 
    drop if court_id == "cadc" | court_id == "cafc" | court_id == "scotus"
    // tab _merge
    * assert that there are no unmerged cases
    assert _merge == 3
    drop _merge
    // exit 

    encode court_id, gen(court_id_code)
    xtset court_id_code year

    gen double adverse_rulings_pc = (n_adverse_rulings / population) * 100000 // per capita (100k) rate
    gen double adverse_rulings_pc_lag1 = L.adverse_rulings_pc
    gen double judge_iv_lag1 = L.judge_iv

    label variable spend_per_mile "Highway Cost per Mile (\textdollar B, 2016 USD)"
    label variable adverse_rulings_pc "Adverse Rulings per 100k"
    label variable adverse_rulings_pc_lag1 "Adverse Rulings per 100k (t-1)"
    label variable judge_iv "Judge Strictness IV"
    label variable judge_iv_lag1 "Judge Strictness IV (t-1)"

    * Basic regression
    eststo ols_t: reg spend_per_mile adverse_rulings_pc i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_lag1: reg spend_per_mile adverse_rulings_pc_lag1 i.year i.court_id_code, vce(cluster court_id_code)

    * Judge IV first stage
    eststo fs_t: reg adverse_rulings_pc judge_iv i.year i.court_id_code, vce(cluster court_id_code)
    eststo fs_lag1: reg adverse_rulings_pc_lag1 judge_iv_lag1 i.year i.court_id_code, vce(cluster court_id_code)

    * Judge IV second stage
    eststo iv_t: ivreg2 spend_per_mile i.year i.court_id_code (adverse_rulings_pc = judge_iv), partial(i.year i.court_id_code) cluster(court_id_code)
    eststo iv_lag1: ivreg2 spend_per_mile i.year i.court_id_code (adverse_rulings_pc_lag1 = judge_iv_lag1), partial(i.year i.court_id_code) cluster(court_id_code)
    // note we absorb FE via partial in order to avoid some computational errors

    * sanity-check the IV implementation w another package
    eststo ivr_t: ivregress 2sls spend_per_mile i.year i.court_id_code (adverse_rulings_pc = judge_iv), vce(cluster court_id_code)
    eststo ivr_lag1: ivregress 2sls spend_per_mile i.year i.court_id_code (adverse_rulings_pc_lag1 = judge_iv_lag1), vce(cluster court_id_code)

    esttab ols_t ols_lag1 fs_t fs_lag1 iv_t iv_lag1 ivr_t ivr_lag1 ///
        using "${tabdir}/judgeIV_cost_regressions.tex", replace ///
        booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
        drop(_cons) ///
        mtitles("$\textdollar$ / Mile" "$\textdollar$ / Mile" ///
            "\shortstack{Adverse Rulings\\per 100k}" "\shortstack{Adverse Rulings\\per 100k (t-1)}" ///
            "$\textdollar$ per Mile" "$\textdollar$ per Mile" ///
            "$\textdollar$ per Mile" "$\textdollar$ per Mile") ///
        mgroups("OLS" "First Stage" "2SLS (ivreg2)" "2SLS (ivregress)", pattern(1 0 1 0 1 0 1 0) span ///
            prefix(\multicolumn{2}{c}{) suffix(})) ///
        indicate("Year FE = *.year" "Circuit FE = *.court_id_code", labels("X" "")) ///
        scalars("N Observations" "r2_a Adj. R\textsuperscript{2}" "widstat First-stage F-stat") ///
        sfmt(%9.0fc %9.3f %9.2f) ///
        nonumber ///
        nonotes
    copy_tab_to_overleaf "judgeIV_cost_regressions.tex"

}

* ==============================================================================
* Judge IV second stage, 6-yr periods
* ==============================================================================
if $judgeIV_6yr == 1 {

    use `case_level', clear

    gen byte adverse_ruling = .
    replace adverse_ruling = 1 if prevailing_party == "plaintiff"
    replace adverse_ruling = 0 if prevailing_party == "defendant"

    * convert case data to 6-yr bins (note Brooks Liscow labels bins by end year)
    gen int period = 1963 + 6 * ceil((year - 1963) / 6)

    * collapse to circuit x period
    collapse (sum) n_adverse_rulings = adverse_ruling ///
        (mean) judge_iv = c_strict_prevailing_score ///
        (count) n_cases = case_id, ///
        by(court_id period)
    tab court_id period

    fillin court_id period
    replace n_adverse_rulings = 0 if _fillin
    replace n_cases = 0 if _fillin
    drop _fillin

    tempfile circuit_period_cases
    save `circuit_period_cases'

    * to merge highway data to appellate circuit
    import delimited "${data_dir}/Raw/state_to_circuit_crosswalk.csv", varnames(1) clear
    keep state_abbrev court_id
    rename state_abbrev state_abrev
    tempfile crosswalk_abrev
    save `crosswalk_abrev'

    * clean population data
    * can't use the population data from the 6-yr file since it's a 6-year sum and is missing where no miles were built
    use "${data_dir}/Raw/Brooks Liscow/Annual_In-House_Dataset.dta", clear
    drop if state_name == "US_Total"
    keep state_abrev YEAR pop
    gen int period = 1963 + 6 * ceil((YEAR - 1963) / 6)
    collapse (mean) pop, by(state_abrev period)
    merge m:1 state_abrev using `crosswalk_abrev', keep(match) nogen
    collapse (sum) population = pop, by(court_id period) // collapse to circuit and period level
    drop if period < 1970 | period > 1993
    tempfile circuit_period_pop
    save `circuit_period_pop'

    * re-compute spend per mile aggregated to circuit level
    use "${data_dir}/Raw/Brooks Liscow/6yr_In-House_Dataset.dta", clear
    keep state_abrev period_5yr lag_scaled_spending allMiles
    rename period_5yr period // these are the 6-yr bins but named incorrectly in the Brooks Liscow data
    merge m:1 state_abrev using `crosswalk_abrev', keep(match) nogen
    collapse (sum) lag_scaled_spending allMiles, by(court_id period)
    gen spend_per_mile = lag_scaled_spending / allMiles
    drop if period < 1970 | period > 1993
    merge 1:1 court_id period using `circuit_period_pop', assert(match) nogen
    tempfile circuit_period_spending
    save `circuit_period_spending'

    use `circuit_period_cases', clear
    merge 1:1 court_id period using `circuit_period_spending'
    drop if period < 1970 | period > 1993
    drop if court_id == "cadc" | court_id == "cafc" | court_id == "scotus"
    assert _merge == 3
    drop _merge

    encode court_id, gen(court_id_code)
    xtset court_id_code period, delta(6)

    gen double adverse_rulings_pc = (n_adverse_rulings / population) * 100000
    gen double adverse_rulings_pc_lag1 = L.adverse_rulings_pc
    gen double judge_iv_lag1 = L.judge_iv

    label variable spend_per_mile "Highway Cost per Mile (\textdollar B, 2016 USD)"
    label variable adverse_rulings_pc "Adverse Rulings per 100k"
    label variable adverse_rulings_pc_lag1 "Adverse Rulings per 100k (t-1)"
    label variable judge_iv "Judge Strictness IV"
    label variable judge_iv_lag1 "Judge Strictness IV (t-1)"

    eststo clear

    eststo ols6_t: reg spend_per_mile adverse_rulings_pc i.period i.court_id_code, vce(cluster court_id_code)
    eststo ols6_lag1: reg spend_per_mile adverse_rulings_pc_lag1 i.period i.court_id_code, vce(cluster court_id_code)

    eststo fs6_t: reg adverse_rulings_pc judge_iv i.period i.court_id_code, vce(cluster court_id_code)
    eststo fs6_lag1: reg adverse_rulings_pc_lag1 judge_iv_lag1 i.period i.court_id_code, vce(cluster court_id_code)

    eststo iv6_t: ivreg2 spend_per_mile i.period i.court_id_code (adverse_rulings_pc = judge_iv), partial(i.period i.court_id_code) cluster(court_id_code)
    eststo iv6_lag1: ivreg2 spend_per_mile i.period i.court_id_code (adverse_rulings_pc_lag1 = judge_iv_lag1), partial(i.period i.court_id_code) cluster(court_id_code)

    esttab ols6_t ols6_lag1 fs6_t fs6_lag1 iv6_t iv6_lag1 ///
        using "${tabdir}/judgeIV_cost_regressions_6yr.tex", replace ///
        booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
        drop(_cons) ///
        mtitles("$\textdollar$ / Mile" "$\textdollar$ / Mile" ///
            "\shortstack{Adverse Rulings\\per 100k}" "\shortstack{Adverse Rulings\\per 100k (t-1)}" ///
            "$\textdollar$ per Mile" "$\textdollar$ per Mile") ///
        mgroups("OLS" "First Stage" "IV (2SLS)", pattern(1 0 1 0 1 0) span ///
            prefix(\multicolumn{2}{c}{) suffix(})) ///
        indicate("Period FE = *.period" "Circuit FE = *.court_id_code", labels("X" "")) ///
        scalars("N Observations" "r2_a Adj. R\textsuperscript{2}" "widstat First-stage F-stat") ///
        sfmt(%9.0fc %9.3f %9.2f) ///
        nonumber ///
        nonotes
    copy_tab_to_overleaf "judgeIV_cost_regressions_6yr.tex"

}
