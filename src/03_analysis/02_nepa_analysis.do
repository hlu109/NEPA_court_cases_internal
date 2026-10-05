/*==============================================================================
	This script runs summary stats and first stage tests of judge instruments. 
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
    global hannah_loc = "docker"
    if strpos("`cwd'", "pi_zdl3") {
        global dropbox "/nfs/roberts/project/pi_zdl3/shared/NEPA court case project"
        global code_dir "${dropbox}/Code/NEPA_court_cases_internal"
    }
    else if "$hannah_loc" == "dropbox" {
        global dropbox "C:/Users/hl2266/YLS Dropbox/Hannah Lu/shared/NEPA Court Cases (Internal)"
        global code_dir "${dropbox}/Code/NEPA_court_cases_internal"
    }
    else if "$hannah_loc" == "docker" {
        global dropbox "C:/Users/hl2266/YLS Dropbox/Hannah Lu/shared/NEPA Court Cases (Internal)"
        global code_dir "C:/Users/hl2266/project_dockers/nepa/Code/NEPA_court_cases_internal"
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
global prelim_analysis = 1
global judgeIV_stage1 = 1
* ==============================================================================

* ------------------------------------------------------------------
* Load + clean case-level data
* ------------------------------------------------------------------
if $prelim_analysis == 1 | $judgeIV_stage1 == 1 {

    insheet using "${data_dir}/Intermediate/Feature Classification Predictions/courtlistener_metadata_w_extracted_features.csv", clear

    * track number of cases before and after duplicate cleaning
    count
    local n_raw = r(N)

    * Collapse duplicate opinions
    * TODO: move this upstream into 05_build_case_file.py
    keep lead_opinion_id cluster_id court court_id datefiled year_filed casename docket_numbers_parsed docket_no1 docket_no2 docket_no3 docket_no4 docket_no5 citation source file_source_indicator ///
        district_outcome disposition prevailing_party district_score disposition_score prevailing_score pro_dev_district_score pro_dev_prevailing_score ///
        panel_judges panel_judge_count en_banc panel_judge_1 panel_judge_2 panel_judge_3 panel_judge_full_name_1 panel_judge_full_name_2 panel_judge_full_name_3 panel_judge_nid_1 panel_judge_nid_2 panel_judge_nid_3 panel_all_matched ///
        panel_judge_dem_? panel_judge_rep_? panel_judge_female_? panel_judge_poc_? panel_judge_fedpros_?

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

    * anti-development outcome score: 1 anti-development, 0.5 mixed, 0 pro-development
    gen double anti_dev_score = 1 - pro_dev_prevailing_score
    label variable anti_dev_score "Anti-Development Ruling"

    /* Some Simple Summary Stats*/
    * judge missing
    tab panel_judge_count, mi
    replace panel_judge_count = 0 if mi(panel_judge_count)
    tab panel_judge_count, mi
    gen judge_miss = (panel_judge_count == 0)
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
            legend(order(1 "All" 3 "Defendant" 2 "Plaintiff" 4 "Mixed") rows(4) cols(1) size(vsmall) position(3) region(lstyle(none))) ///
            ytitle("Number of Cases") xtitle("Year Appellate Case Decided") ///
            xlabel(1970(10)2025) xscale(range(1970 2025)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/cases_over_time_district_outcome.png", replace width(1200)
        copy_fig_to_overleaf "cases_over_time_district_outcome.png"
    restore

    * -- compare appellate outcomes
    preserve
        gen byte anti_dev = (anti_dev_score == 1)
        gen byte pro_dev = (anti_dev_score == 0)
        gen byte mixed = (anti_dev_score == 0.5)

        collapse (sum) n_total = one (sum) anti_dev (sum) pro_dev (sum) mixed, by(year)
        sort year

        twoway (line n_total year) ///
               (line anti_dev year) ///
               (line pro_dev year) ///
               (line mixed year), ///
            legend(order(1 "All" 3 "Pro-Development" 2 "Anti-Development" 4 "Mixed") rows(4) size(vsmall) position(3) region(lstyle(none))) ///
            ytitle("Number of Cases") xtitle("Year Decided") ///
            xlabel(1970(10)2025) xscale(range(1970 2025)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/cases_over_time_anti_dev.png", replace width(1200)
        copy_fig_to_overleaf "cases_over_time_anti_dev.png"
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
            legend(order(1 "All" 3 "Affirm" 2 "Reversal" 4 "Mixed") rows(4) size(vsmall) position(3) region(lstyle(none))) ///
            ytitle("Number of Cases") xtitle("Year Decided") ///
            xlabel(1970(10)2025) xscale(range(1970 2025)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/cases_over_time_disposition.png", replace width(1200)
        copy_fig_to_overleaf "cases_over_time_disposition.png"
    restore

}

* ------------------------------------------------------------------
* Judge IV first stage
* ------------------------------------------------------------------
if $judgeIV_stage1 == 1 {

    * ============================================================
    * Step 1: Set aside cases with no judges matched to FJC records (to append back after judge processing)
    * ============================================================
    gen case_id = _n

    * a judge without an FJC id is treated as missing, but we keep partially matched panels for the judge-level stats for now
    gen byte no_judge = mi(panel_judge_nid_1) & mi(panel_judge_nid_2) & mi(panel_judge_nid_3)
    egen byte n_judges_matched = rownonmiss(panel_judge_nid_1 panel_judge_nid_2 panel_judge_nid_3)

    preserve
        keep if no_judge
        tempfile no_judge_cases
        save `no_judge_cases'
    restore
    drop if no_judge

    * construct demographic indicators including interactions as potential IVs
    * first build the indicators at the judge level
    forvalues k = 1/3 {
        gen byte panel_judge_male_`k' = 1 - panel_judge_female_`k'
        gen byte panel_judge_white_`k' = 1 - panel_judge_poc_`k'
    }
    global iv_singles rep poc female fedpros
    global iv_pairs 
    foreach p in dem rep {
        foreach r in poc white {
            global iv_pairs $iv_pairs `p'_`r'
        }
        foreach g in female male {
            global iv_pairs $iv_pairs `p'_`g'
        }
    }
    foreach r in poc white {
        foreach g in female male {
            global iv_pairs $iv_pairs `r'_`g'
        }
    }
    * split the 12 demographic pair IVs across two tables
    global iv_pairs1
    global iv_pairs2
    forvalues k = 1/12 {
        local pr : word `k' of $iv_pairs
        if `k' <= 6 {
            global iv_pairs1 $iv_pairs1 `pr'
        }
        else {
            global iv_pairs2 $iv_pairs2 `pr'
        }
    }
    global iv_triples 
    foreach p in dem rep {
        foreach r in poc white {
            foreach g in female male {
                global iv_triples $iv_triples `p'_`r'_`g'
            }
        }
    }
    foreach c in $iv_pairs $iv_triples rep_fedpros {
        local parts = subinstr("`c'", "_", " ", .)
        forvalues k = 1/3 {
            gen byte panel_judge_`c'_`k' = 1
            foreach x of local parts {
                quietly replace panel_judge_`c'_`k' = panel_judge_`c'_`k' * panel_judge_`x'_`k'
            }
        }
    }
    * now consolidate indicators to the case level, compute counts of judges with each characteristic
    global iv_instruments $iv_singles $iv_pairs $iv_triples rep_fedpros dem white male // dem, white, male are built only for the histograms and not tested as instruments
    foreach x of global iv_instruments {
        egen count_`x' = rowtotal(panel_judge_`x'_?), missing
        egen n_known = rownonmiss(panel_judge_`x'_?)
        replace count_`x' = . if n_known != panel_judge_count
        drop n_known
    }
    * create readable instrument names for table labels (e.g. rep_poc -> Rep. POC)
    foreach x of global iv_instruments {
        local lab
        foreach w in `=subinstr("`x'", "_", " ", .)' {
            if "`w'" == "dem" local w "Dem."
            else if "`w'" == "rep" local w "Rep."
            else if "`w'" == "poc" local w "POC"
            else if "`w'" == "white" local w "White"
            else if "`w'" == "female" local w "Female"
            else if "`w'" == "male" local w "Male"
            else if "`w'" == "fedpros" local w "Fed. Pros."
            local lab `lab' `w'
        }
        local lab_`x' `lab'
        label variable count_`x' "Num. `lab'"
    }
    foreach x of global iv_instruments {
        drop panel_judge_`x'_?
    }

    * ============================================================
    * Step 2: Reshape to judge-level
    * ============================================================
    reshape long panel_judge_ panel_judge_full_name_ panel_judge_nid_, i(case_id) j(judge_num)
    rename panel_judge_nid_ judge_id
    drop if mi(judge_id)
    rename panel_judge_full_name_ judge_name // name label for figures

    * ============================================================
    * Step 3: Count cases per judge
    * ============================================================
    bysort judge_id: gen case_count_per_judge = _N

    * ============================================================
    * Step 4: Create binary indicator for judges with 10+ observations
    * ============================================================
    levelsof judge_id if case_count_per_judge >= 10, local(freq_judges)
    foreach j of local freq_judges {
        gen byte d_`j' = (judge_id == `j')
    }

    * ============================================================
    * Step 5: Leave-one-out judge strictness measures
    * ============================================================
    * --- Compute leave-one-out means relative to court average ---
    foreach var in district_score disposition_score anti_dev_score {

        bysort judge_id: egen double sum_j_`var' = total(`var')
        bysort judge_id: egen long   n_j_`var'   = count(`var')
        gen double loo_judge_`var' = (sum_j_`var' - `var') / (n_j_`var' - 1) if n_j_`var' > 1

        bysort court: egen double mean_court_`var' = mean(`var')

        gen double strictness_`var' = loo_judge_`var' - mean_court_`var'

        drop sum_j_`var' n_j_`var' loo_judge_`var' mean_court_`var'
    }

    * --- Create strictness versions at two cutoffs ---
    foreach var in district_score disposition_score anti_dev_score {
        gen double strictness10_`var' = strictness_`var'
        replace strictness10_`var' = . if case_count_per_judge < 10

        gen double strictness20_`var' = strictness_`var'
        replace strictness20_`var' = . if case_count_per_judge < 20
    }

    * --- Top 10 and Bottom 10 judges by anti-development strictness ---
    preserve
        bysort judge_id: keep if _n == 1
        keep if !missing(strictness_anti_dev_score) & case_count_per_judge >= 10
        keep judge_name case_count_per_judge strictness_anti_dev_score
        gsort -strictness_anti_dev_score
        gen rank = _n
        local N = _N

        * Top 10 plaintiff-leaning
        graph hbar strictness_anti_dev_score if rank <= 10, ///
            over(judge_name, sort(strictness_anti_dev_score) descending label(labsize(vsmall))) ///
            ytitle("Strictness (Anti-Development)") ///
            bar(1, color(navy)) ///
            blabel(bar, size(vsmall) format(%5.3f)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/top10_judges.png", replace width(1200)
        copy_fig_to_overleaf "top10_judges.png"

        * Bottom 10 defendant-leaning
        graph hbar strictness_anti_dev_score if rank > `N' - 10, ///
            over(judge_name, sort(strictness_anti_dev_score) label(labsize(vsmall))) ///
            ytitle("Strictness (Anti-Development)") ///
            bar(1, color(maroon)) ///
            blabel(bar, size(vsmall) format(%5.3f)) ///
            scheme(s2color) graphregion(color(white))
        graph export "${figdir}/bottom10_judges.png", replace width(1200)
        copy_fig_to_overleaf "bottom10_judges.png"
    restore


    eststo clear

    * --- Cutoff = 10 ---
    eststo j10_antidev: reg anti_dev_score  strictness10_anti_dev_score i.year i.numeric_court
    eststo j10_dist: reg district_score    strictness10_district_score i.year i.numeric_court
    eststo j10_disp: reg disposition_score strictness10_disposition_score i.year i.numeric_court

    * --- Cutoff = 20 ---
    eststo j20_antidev: reg anti_dev_score  strictness20_anti_dev_score i.year i.numeric_court
    eststo j20_dist: reg district_score    strictness20_district_score i.year i.numeric_court
    eststo j20_disp: reg disposition_score strictness20_disposition_score i.year i.numeric_court

    * --- No cutoff ---
    eststo jnc_antidev: reg anti_dev_score  strictness_anti_dev_score i.year i.numeric_court
    eststo jnc_dist: reg district_score    strictness_district_score i.year i.numeric_court
    eststo jnc_disp: reg disposition_score strictness_disposition_score i.year i.numeric_court

    * --- No cutoff, weighted by judge caseload ---
    eststo jwt_antidev: reg anti_dev_score  strictness_anti_dev_score   i.year i.numeric_court [aw=case_count_per_judge]
    eststo jwt_dist: reg district_score    strictness_district_score   i.year i.numeric_court [aw=case_count_per_judge]
    eststo jwt_disp: reg disposition_score strictness_disposition_score i.year i.numeric_court [aw=case_count_per_judge]

    * --- Table: Judge-level, by outcome ---
    foreach outcome in antidev dist disp {
        if "`outcome'" == "antidev" local deplab "Anti-Development Ruling"
        if "`outcome'" == "dist" local deplab "District Outcome"
        if "`outcome'" == "disp" local deplab "Disposition"

        esttab j10_`outcome' j20_`outcome' jnc_`outcome' jwt_`outcome' ///
            using "${tabdir}/judge_level_`outcome'.tex", replace ///
            booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
            nomtitles ///
            mgroups("10 Cutoff" "20 Cutoff" "No Cutoff" "Weighted", ///
                pattern(1 1 1 1)) ///
            indicate("Year FE = *.year" "Court FE = *.numeric_court") ///
            scalars("N Observations" "r2_a Adj. R\textsuperscript{2}") ///
            sfmt(%9.0fc %9.3f) ///
            nonumber ///
            nonotes
        copy_tab_to_overleaf "judge_level_`outcome'.tex"
    }


    * ============================================================
    * Step 6: Roll up to case level
    * ============================================================

    * Average strictness across judges on the panel for each case
    foreach var in district_score disposition_score anti_dev_score {
        bysort case_id: egen double c_strict10_`var' = mean(strictness10_`var')
        bysort case_id: egen double c_strict20_`var' = mean(strictness20_`var')
        bysort case_id: egen double c_strict_`var'   = mean(strictness_`var')
    }

    * Precision weight: minimum case_count_per_judge across panel judges
    bysort case_id: egen double min_judge_case_count = min(case_count_per_judge)

    duplicates drop case_id, force

    * Append back cases with no judge info for the summary stat figure (drop again later)
    append using `no_judge_cases'

    * bar chart of cases by panel type (before dropping en banc cases)
    gen byte panel_type = 3
    replace panel_type = 1 if panel_judge_count == 3 & en_banc != 1 & panel_all_matched == 1
    replace panel_type = 2 if panel_judge_count == 3 & en_banc != 1 & panel_all_matched != 1
    label define panel_type_lbl 1 "3-Judge Panel, All Matched" 2 "3-Judge Panel, Not All Matched" 3 "Other Panel Sizes"
    label values panel_type panel_type_lbl
    graph bar (sum) one, over(panel_type, relabel(1 `" "3-Judge Panel," "All Matched" "' 2 `" "3-Judge Panel," "Not All Matched" "' 3 `" "Other Panel" "Sizes" "') label(labsize(*1.2))) ///
        ylabel(, labsize(*1.2)) ///
        ytitle("Number of Cases", size(*1.2)) ///
        bar(1)
    graph export "${figdir}/panel_type_bar.png", replace width(1200)
    copy_fig_to_overleaf "panel_type_bar.png"
    drop panel_type

    * drop en banc cases 
    drop if en_banc == 1

    * number of judge summaries
    tab panel_judge_count
    histogram panel_judge_count, discrete frequency ///
        xlabel(0(1)16) ///
        xtitle("Number of Judges on Panel") ///
        ytitle("Number of Cases") ///
        color(navy) ///
        scheme(s2color) graphregion(color(white))
    graph export "${figdir}/panel_size_hist.png", replace width(1200)
    copy_fig_to_overleaf "panel_size_hist.png"

    * number of panel judges matched to an FJC record
    histogram n_judges_matched, discrete frequency ///
        xlabel(0(1)3, labsize(*1.2)) ylabel(, labsize(*1.2)) ///
        xtitle("Number of Judges Matched to FJC Records", size(*1.2)) ///
        ytitle("Number of Cases", size(*1.2))
    graph export "${figdir}/judges_matched_hist.png", replace width(1200)
    copy_fig_to_overleaf "judges_matched_hist.png"
    drop n_judges_matched

    * for the rest of the analysis, keep only 3-judge, non-en-banc panels where every judge is matched to an FJC record
    gen byte iv_sample = (panel_judge_count == 3 & panel_all_matched == 1)
    keep if iv_sample


    eststo clear

    * --- Cutoff = 10 ---
    eststo c10_antidev: reg anti_dev_score  c_strict10_anti_dev_score i.year i.numeric_court
    eststo c10_disp: reg disposition_score c_strict10_disposition_score i.year i.numeric_court
    eststo c10_dist: reg district_score    c_strict10_district_score    i.year i.numeric_court

    * --- Cutoff = 20 ---
    eststo c20_antidev: reg anti_dev_score  c_strict20_anti_dev_score i.year i.numeric_court
    eststo c20_disp: reg disposition_score c_strict20_disposition_score i.year i.numeric_court
    eststo c20_dist: reg district_score    c_strict20_district_score    i.year i.numeric_court

    * --- No cutoff, weighted by min panel judge caseload ---
    eststo cwt_antidev: reg anti_dev_score  c_strict_anti_dev_score i.year i.numeric_court [aw=min_judge_case_count]
    eststo cwt_disp: reg disposition_score c_strict_disposition_score i.year i.numeric_court [aw=min_judge_case_count]
    eststo cwt_dist: reg district_score    c_strict_district_score    i.year i.numeric_court [aw=min_judge_case_count]

    * --- Table: Case-level, by outcome ---
    foreach outcome in antidev dist disp {
        if "`outcome'" == "antidev" local deplab "Anti-Development Ruling"
        if "`outcome'" == "dist" local deplab "District Outcome"
        if "`outcome'" == "disp" local deplab "Disposition"

        esttab c10_`outcome' c20_`outcome' cwt_`outcome' ///
            using "${tabdir}/case_level_`outcome'.tex", replace ///
            booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
            nomtitles ///
            mgroups("10 Cutoff" "20 Cutoff" "Weighted", ///
                pattern(1 1 1)) ///
            indicate("Year FE = *.year" "Court FE = *.numeric_court") ///
            scalars("N Observations" "r2_a Adj. R\textsuperscript{2}") ///
            sfmt(%9.0fc %9.3f) ///
            nonumber ///
            nonotes
        copy_tab_to_overleaf "case_level_`outcome'.tex"
    }

    * ============================================================
    * Step 7: First stage tests of panel composition instruments (case level)
    * ============================================================
    label variable district_score "District Outcome"
    label variable disposition_score "Disposition"
    foreach outcome in antidev dist disp {
        if "`outcome'" == "antidev" local y anti_dev_score
        if "`outcome'" == "dist" local y district_score
        if "`outcome'" == "disp" local y disposition_score

        foreach group in singles pairs1 pairs2 triples {
            eststo clear
            foreach x of global iv_`group' {
                quietly eststo `x': reg `y' count_`x' i.year i.numeric_court if iv_sample
                * first-stage F-test of the instrument (with one instrument this equals the squared t-stat)
                quietly test count_`x'
                estadd scalar F_stat = r(F) : `x'
                quietly sum count_`x' if e(sample)
                estadd scalar mean_count = r(mean) : `x'
                quietly sum `y' if e(sample)
                estadd scalar mean_y = r(mean) : `x'
            }
            * format dependent variable column headers
            local ylab : variable label `y'
            local n_models : word count ${iv_`group'}
            local pattern = "1" + " 0" * (`n_models' - 1)
            esttab ${iv_`group'} using "${tabdir}/fs_panel_composition_`outcome'_`group'.tex", replace ///
                booktabs label nomtitles se star(* 0.10 ** 0.05 *** 0.01) ///
                mgroups("`ylab'", pattern(`pattern') prefix(\multicolumn{@span}{c}{) suffix(}) span) ///
                drop(_cons) ///
                indicate("Year FE = *.year" "Court FE = *.numeric_court", labels("X" "")) ///
                scalars("F_stat First-stage F-stat" "mean_count Mean of instrument" "mean_y Mean of dep. var." "N Observations" "r2_a Adj. R\textsuperscript{2}") ///
                sfmt(%9.2f %9.2f %9.3f %9.0fc %9.3f) ///
                nonotes
            copy_tab_to_overleaf "fs_panel_composition_`outcome'_`group'.tex"
        }
    }

    * export the case-level data with strictness measures and instrument counts for later 2SLS analysis
    cap mkdir "${data_dir}/Intermediate/Judge IV"
    save "${data_dir}/Intermediate/Judge IV/judge_iv_case_level.dta", replace

    * ============================================================
    * Step 8: Construct circuit-year panel 
    * ============================================================
    * "adverse ruling" = anti-development ruling - NEPA gets stricter
    // for now we drop cases with mixed or missing outcomes, TBD if we want to include mixed results back in
    gen adverse_ruling = anti_dev_score if anti_dev_score != 0.5
    gen byte mixed_ruling = (anti_dev_score == 0.5) if !missing(anti_dev_score)

    assert !(court_id == "ca11" & year <= 1981) // 11th circuit split from the 5th on 10/1/1981

    * aggregate the demographic instruments to be number of cases with at least one judge with X characteristic
    local ncases_stats // define an empty local to store the collapse commands
    foreach x of global iv_instruments {
        gen byte has_`x' = (count_`x' > 0) if !missing(count_`x')
        local ncases_stats `ncases_stats' (sum) ncases_`x' = has_`x'
    }

    * collapse to circuit x year
    collapse (sum) n_adverse_rulings = adverse_ruling ///
        (count) n_clear_rulings = adverse_ruling ///
        (sum) n_mixed = mixed_ruling ///
        (mean) share_adverse = adverse_ruling ///
        (mean) strictness = c_strict_anti_dev_score ///
        `ncases_stats' ///
        (count) n_cases = case_id, ///
        by(court_id year)
    gen n_pro_dev = n_clear_rulings - n_adverse_rulings // just for summary stats
    drop n_clear_rulings
    foreach x of global iv_instruments {
        label variable ncases_`x' "Num. cases w/ `lab_`x''"
    }

    * fill in circuit-year observations with zero NEPA cases
    fillin court_id year
    foreach v in n_adverse_rulings n_pro_dev n_mixed n_cases {
        replace `v' = 0 if _fillin
    }
    drop _fillin
    drop if court_id == "ca11" & year <= 1981 // 11th circuit did not exist yet

    * set the instruments to 0 in circuit-years with no cases and control for whether there were any cases
    gen byte has_cases = (n_cases > 0)
    foreach v of varlist strictness ncases_* {
        quietly replace `v' = 0 if !has_cases
    }

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
    replace court_id = "ca5" if inlist(state_name, "Alabama", "Florida", "Georgia") & year <= 1981 // 5th circuit before the 11th circuit split

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

    gen double adverse_rulings_percap = (n_adverse_rulings / population) * 10000000 // per capita (per 10 million) rate
    gen double adverse_rulings_percap_lag1 = L.adverse_rulings_percap
    gen double share_adverse_lag1 = L.share_adverse
    gen double n_adverse_rulings_lag1 = L.n_adverse_rulings
    gen double strictness_lag1 = L.strictness
    gen byte has_cases_lag1 = L.has_cases
    gen double n_cases_lag1 = L.n_cases
    gen double population_lag1 = L.population

    label variable spend_per_mile "Highway Cost per Mile (\textdollar B, 2016 USD)"
    label variable adverse_rulings_percap "Adverse Rulings per 10 Million"
    label variable adverse_rulings_percap_lag1 "Adverse Rulings per 10 Million (t-1)"
    label variable share_adverse "Share of Adverse Rulings"
    label variable share_adverse_lag1 "Share of Adverse Rulings (t-1)"
    label variable n_adverse_rulings "Adverse Rulings"
    label variable n_adverse_rulings_lag1 "Adverse Rulings (t-1)"
    label variable strictness "Judge Strictness IV"
    label variable strictness_lag1 "Judge Strictness IV (t-1)"
    label variable has_cases "Has NEPA Cases"
    label variable has_cases_lag1 "Has NEPA Cases (t-1)"
    label variable n_cases "Num. NEPA Cases"
    label variable n_cases_lag1 "Num. NEPA Cases (t-1)"
    label variable population "Population"
    label variable population_lag1 "Population (t-1)"


    * export the circuit-year panel for the 2SLS analysis in 03_judge_iv.do
    save "${data_dir}/Intermediate/Judge IV/judge_iv_circuit_year.dta", replace

    * ============================================================
    * Step 9: Summary stats for the circuit-year panel
    * ============================================================
    * look at variation in the treatment across circuit-years, raw and net of circuit and year FE (the variation the regressions use)
    label variable n_cases "Number of NEPA Cases"
    label variable n_adverse_rulings "Number of Anti-Development Rulings"
    label variable n_pro_dev "Number of Pro-Development Rulings"
    label variable n_mixed "Number of Mixed Rulings"
    label variable share_adverse "Share of Anti-Development Rulings"
    local sumvars n_adverse_rulings share_adverse adverse_rulings_percap
    local residvars
    foreach v of local sumvars {
        quietly reg `v' i.year i.court_id_code
        predict double resid_`v' if e(sample), residuals
        local lab : variable label `v'
        label variable resid_`v' "`lab' Residual (net of circuit and year FE)"
        local residvars `residvars' resid_`v'
    }
    eststo clear
    * export summary stats table with case counts by outcome at the top, then the treatment measures raw and residualized
    estpost tabstat n_cases n_adverse_rulings n_pro_dev n_mixed share_adverse adverse_rulings_percap `residvars', statistics(count mean sd min p50 max) columns(statistics)
    esttab using "${tabdir}/sumstats_adverse_rulings.tex", replace ///
        cells("count(fmt(%9.0fc)) mean(fmt(3)) sd(fmt(3)) min(fmt(3)) p50(fmt(3)) max(fmt(3))") ///
        collabels("N" "Mean" "SD" "Min" "Median" "Max") ///
        booktabs label noobs nonumber nomtitles ///
        nonotes
    copy_tab_to_overleaf "sumstats_adverse_rulings.tex"
    drop `residvars'

    histogram n_adverse_rulings, discrete frequency ///
        xtitle("Adverse Rulings", size(*2)) ytitle("Frequency", size(*2)) xlabel(, labsize(*2)) ylabel(, labsize(*2))
    graph export "${figdir}/hist_adverse_count.png", replace width(1200)
    copy_fig_to_overleaf "hist_adverse_count.png"

    histogram adverse_rulings_percap, frequency ///
        xtitle("Adverse Rulings per 10 Million", size(*2)) ytitle("Frequency", size(*2)) xlabel(, labsize(*2)) ylabel(, labsize(*2))
    graph export "${figdir}/hist_adverse_count_percapita.png", replace width(1200)
    copy_fig_to_overleaf "hist_adverse_count_percapita.png"

    histogram share_adverse, frequency ///
        xtitle("Share of Adverse Rulings", size(*2)) ytitle("Frequency", size(*2)) xlabel(, labsize(*2)) ylabel(, labsize(*2))
    graph export "${figdir}/hist_adverse_share.png", replace width(1200)
    copy_fig_to_overleaf "hist_adverse_share.png"

    histogram strictness if has_cases, frequency ///
        xtitle("Mean Panel Strictness" "(Anti-Development)", size(*2)) ytitle("Frequency", size(*2)) xlabel(, labsize(*2)) ylabel(, labsize(*2))
    graph export "${figdir}/hist_strictness.png", replace width(1200)
    copy_fig_to_overleaf "hist_strictness.png"

    histogram ncases_dem_poc if has_cases, discrete frequency ///
        xtitle("Cases with at Least One" "POC Democrat", size(*2)) ytitle("Frequency", size(*2)) xlabel(, labsize(*2)) ylabel(, labsize(*2))
    graph export "${figdir}/hist_ncases_dem_poc.png", replace width(1200)
    copy_fig_to_overleaf "hist_ncases_dem_poc.png"

    histogram ncases_rep_fedpros if has_cases, discrete frequency ///
        xtitle("Cases with at Least One Republican" "Former Federal Prosecutor", size(*2)) ytitle("Frequency", size(*2)) xlabel(, labsize(*2)) ylabel(, labsize(*2))
    graph export "${figdir}/hist_ncases_rep_fedpros.png", replace width(1200)
    copy_fig_to_overleaf "hist_ncases_rep_fedpros.png"

    foreach x in dem rep female male poc white {
        if "`x'" == "dem" local desc "Democratic Judge"
        if "`x'" == "rep" local desc "Republican Judge"
        if "`x'" == "female" local desc "Female Judge"
        if "`x'" == "male" local desc "Male Judge"
        if "`x'" == "poc" local desc "Person of Color Judge"
        if "`x'" == "white" local desc "White Judge"
        histogram ncases_`x' if has_cases, discrete frequency ///
            xtitle("Cases with at Least One" "`desc'", size(*2)) ytitle("Frequency", size(*2)) xlabel(, labsize(*2)) ylabel(, labsize(*2))
        graph export "${figdir}/hist_ncases_`x'.png", replace width(1200)
        copy_fig_to_overleaf "hist_ncases_`x'.png"
    }

    * ============================================================
    * Step 10: First stage tests at the circuit-year level
    * ============================================================
    * regress each treatment measure on each instrument, with year and circuit FE and SEs clustered by circuit
    * test on 3 potential treatment variables: adverse rulings per 10 million and the number of adverse rulings (both include controls for whether there are any cases), and the share of adverse (anti-development) rulings (only defined in circuit-years with cases)
    label variable ncases_dem_poc "Num. Cases w/ POC Dem."
    label variable ncases_rep_fedpros "Num. Cases w/ Rep. Former Fed. Prosecutor"

    foreach tmt in pc share count {
        if "`tmt'" == "pc" {
            local y adverse_rulings_percap
            local controls has_cases n_cases
        }
        if "`tmt'" == "share" {
            local y share_adverse
            local controls n_cases
        }
        if "`tmt'" == "count" {
            local y n_adverse_rulings
            local controls has_cases n_cases
        }

        * manually selected instruments: strictness, POC Dem, Rep former fed prosecutor, also last two jointly
        local inst_strictness strictness
        local inst_dem_poc ncases_dem_poc
        local inst_rep_fedpros ncases_rep_fedpros
        local inst_joint ncases_dem_poc ncases_rep_fedpros
        eststo clear
        foreach m in strictness dem_poc rep_fedpros joint {
            quietly eststo courtyr_`m': reg `y' `inst_`m'' `controls' i.year i.court_id_code, vce(cluster court_id_code)
            quietly test `inst_`m''
            estadd scalar F_stat = r(F) : courtyr_`m'
            quietly sum `y' if e(sample)
            estadd scalar mean_y = r(mean) : courtyr_`m'
            * mean of the instrument in the estimation sample (skip for the joint specification)
            if "`m'" != "joint" {
                quietly sum `inst_`m'' if e(sample)
                estadd scalar mean_inst = r(mean) : courtyr_`m'
            }
        }
        * format dependent variable column headers
        local ylab : variable label `y'
        esttab courtyr_strictness courtyr_dem_poc courtyr_rep_fedpros courtyr_joint using "${tabdir}/fs_courtyr_`tmt'_main.tex", replace ///
            booktabs label nomtitles se star(* 0.10 ** 0.05 *** 0.01) ///
            mgroups("`ylab'", pattern(1 0 0 0) prefix(\multicolumn{@span}{c}{) suffix(}) span) ///
            order(strictness ncases_dem_poc ncases_rep_fedpros) drop(_cons) ///
            indicate("Year FE = *.year" "Circuit FE = *.court_id_code", labels("X" "")) ///
            scalars("F_stat First-stage F-stat" "mean_inst Mean of instrument" "mean_y Mean of dep. var." "N Observations" "r2_a Adj. R\textsuperscript{2}") ///
            sfmt(%9.2f %9.2f %9.3f %9.0fc %9.3f) ///
            nonotes
        copy_tab_to_overleaf "fs_courtyr_`tmt'_main.tex"

        * test all remaining demographic composition instrument candidates
        foreach group in singles pairs1 pairs2 triples {
            eststo clear
            foreach x of global iv_`group' {
                quietly eststo `x': reg `y' ncases_`x' `controls' i.year i.court_id_code, vce(cluster court_id_code)
                quietly test ncases_`x'
                estadd scalar F_stat = r(F) : `x'
                quietly sum `y' if e(sample)
                estadd scalar mean_y = r(mean) : `x'
                quietly sum ncases_`x' if e(sample)
                estadd scalar mean_ncases = r(mean) : `x'
            }
            * format dependent variable column headers
            local ylab : variable label `y'
            local n_models : word count ${iv_`group'}
            local pattern = "1" + " 0" * (`n_models' - 1)
            * order the instruments first and controls at the bottom
            local order_list
            foreach x of global iv_`group' {
                local order_list `order_list' ncases_`x'
            }
            esttab ${iv_`group'} using "${tabdir}/fs_courtyr_`tmt'_`group'.tex", replace ///
                booktabs label nomtitles se star(* 0.10 ** 0.05 *** 0.01) ///
                mgroups("`ylab'", pattern(`pattern') prefix(\multicolumn{@span}{c}{) suffix(}) span) ///
                order(`order_list') drop(_cons) ///
                indicate("Year FE = *.year" "Circuit FE = *.court_id_code", labels("X" "")) ///
                scalars("F_stat First-stage F-stat" "mean_ncases Mean of instrument" "mean_y Mean of dep. var." "N Observations" "r2_a Adj. R\textsuperscript{2}") ///
                sfmt(%9.2f %9.2f %9.3f %9.0fc %9.3f) ///
                nonotes
            copy_tab_to_overleaf "fs_courtyr_`tmt'_`group'.tex"
        }
    }
    eststo clear

    * ============================================================
    * Step 11: OLS of highway costs on adverse rulings (no instrument)
    * ============================================================
    * test the treatment measures contemporaneous, lagged one year, and lagged five years
    foreach v in adverse_rulings_percap share_adverse n_adverse_rulings has_cases n_cases population {
        gen double `v'_lag5 = L5.`v'
        local lab : variable label `v'
        label variable `v'_lag5 "`lab' (t-5)"
    }

    eststo ols_percap: reg spend_per_mile adverse_rulings_percap has_cases n_cases i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_percap_lag1: reg spend_per_mile adverse_rulings_percap_lag1 has_cases_lag1 n_cases_lag1 i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_percap_lag5: reg spend_per_mile adverse_rulings_percap_lag5 has_cases_lag5 n_cases_lag5 i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_share: reg spend_per_mile share_adverse n_cases i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_share_lag1: reg spend_per_mile share_adverse_lag1 n_cases_lag1 i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_share_lag5: reg spend_per_mile share_adverse_lag5 n_cases_lag5 i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_count: reg spend_per_mile n_adverse_rulings population n_cases has_cases i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_count_lag1: reg spend_per_mile n_adverse_rulings_lag1 population_lag1 n_cases_lag1 has_cases_lag1 i.year i.court_id_code, vce(cluster court_id_code)
    eststo ols_count_lag5: reg spend_per_mile n_adverse_rulings_lag5 population_lag5 n_cases_lag5 has_cases_lag5 i.year i.court_id_code, vce(cluster court_id_code)

    esttab ols_percap ols_percap_lag1 ols_percap_lag5 ols_share ols_share_lag1 ols_share_lag5 ols_count ols_count_lag1 ols_count_lag5 using "${tabdir}/ols_cost_regressions.tex", replace ///
        booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
        order(adverse_rulings_percap adverse_rulings_percap_lag1 adverse_rulings_percap_lag5 share_adverse share_adverse_lag1 share_adverse_lag5 n_adverse_rulings n_adverse_rulings_lag1 n_adverse_rulings_lag5) drop(_cons) ///
        indicate("Has NEPA Cases = has_cases has_cases_lag1 has_cases_lag5" "Num. NEPA Cases = n_cases n_cases_lag1 n_cases_lag5" "Population = population population_lag1 population_lag5" "Year FE = *.year" "Circuit FE = *.court_id_code", labels("X" "")) ///
        mtitles("No Lag" "1-Yr Lag" "5-Yr Lag" "No Lag" "1-Yr Lag" "5-Yr Lag" "No Lag" "1-Yr Lag" "5-Yr Lag") ///
        mgroups("Adverse Rulings per 10 Million" "Share of Adverse Rulings" "Number of Adverse Rulings", pattern(1 0 0 1 0 0 1 0 0) span ///
            prefix(\multicolumn{3}{c}{) suffix(})) ///
        prehead("{" "\def\sym#1{\ifmmode^{#1}\else\(^{#1}\)\fi}" "\begin{tabular}{l*{@M}{c}}" "\toprule" ///
            "&\multicolumn{@M}{c}{Highway Cost per Mile}\\") /// dependent variable printed once above the treatment groups
        scalars("N Observations" "r2_a Adj. R\textsuperscript{2}") ///
        sfmt(%9.0fc %9.3f) ///
        nonotes
    copy_tab_to_overleaf "ols_cost_regressions.tex"
    eststo clear

}
