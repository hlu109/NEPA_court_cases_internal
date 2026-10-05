/*==============================================================================
	This script runs 2SLS judge IV regressions. 
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
global judgeIV_1yr = 1
global judgeIV_6yr = 1
* ==============================================================================

* ==============================================================================
* Judge IV using 1-year periods
* ==============================================================================
if $judgeIV_1yr == 1 {

    * load the circuit-year panel built in 02_nepa_analysis.do
    use "${data_dir}/Intermediate/Judge IV/judge_iv_circuit_year.dta", clear

    * strictness IV
    // * Basic regression
    // eststo ols_t: reg spend_per_mile adverse_rulings_percap has_cases n_cases i.year i.court_id_code, vce(cluster court_id_code)
    // eststo ols_lag1: reg spend_per_mile adverse_rulings_percap_lag1 has_cases_lag1 n_cases_lag1 i.year i.court_id_code, vce(cluster court_id_code)

    // * Judge IV first stage
    // eststo fs_t: reg adverse_rulings_percap strictness has_cases n_cases i.year i.court_id_code, vce(cluster court_id_code)
    // eststo fs_lag1: reg adverse_rulings_percap_lag1 strictness_lag1 has_cases_lag1 n_cases_lag1 i.year i.court_id_code, vce(cluster court_id_code)

    // * Judge IV second stage
    // eststo iv_t: ivreg2 spend_per_mile has_cases n_cases i.year i.court_id_code (adverse_rulings_percap = strictness), partial(i.year i.court_id_code) cluster(court_id_code)
    // eststo iv_lag1: ivreg2 spend_per_mile has_cases_lag1 n_cases_lag1 i.year i.court_id_code (adverse_rulings_percap_lag1 = strictness_lag1), partial(i.year i.court_id_code) cluster(court_id_code)
    // // note we absorb FE via partial in order to avoid some computational errors
    // // TODO: check this

    // * sanity-check the IV implementation w another package
    // eststo ivr_t: ivregress 2sls spend_per_mile has_cases n_cases i.year i.court_id_code (adverse_rulings_percap = strictness), vce(cluster court_id_code)
    // eststo ivr_lag1: ivregress 2sls spend_per_mile has_cases_lag1 n_cases_lag1 i.year i.court_id_code (adverse_rulings_percap_lag1 = strictness_lag1), vce(cluster court_id_code)

    // esttab ols_t ols_lag1 fs_t fs_lag1 iv_t iv_lag1 ivr_t ivr_lag1 ///
    //     using "${tabdir}/judgeIV_cost_regressions.tex", replace ///
    //     booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
    //     drop(_cons) ///
    //     mtitles("\textdollar/Mi" "\textdollar/Mi" ///
    //         "\shortstack{Adverse Rulings\\per 10 Million}" "\shortstack{Adverse Rulings\\per 10 Million (t-1)}" ///
    //         "\textdollar/Mi" "\textdollar/Mi" ///
    //         "\textdollar/Mi" "\textdollar/Mi") ///
    //     mgroups("OLS" "First Stage" "2SLS (ivreg2)" "2SLS (ivregress)", pattern(1 0 1 0 1 0 1 0) span ///
    //         prefix(\multicolumn{2}{c}{) suffix(})) ///
    //     indicate("Year FE = *.year" "Circuit FE = *.court_id_code", labels("X" "")) ///
    //     scalars("N Observations" "r2_a Adj. R\textsuperscript{2}" "widstat First-stage F-stat") ///
    //     sfmt(%9.0fc %9.3f %9.2f) ///
    //     nonumber ///
    //     nonotes
    // copy_tab_to_overleaf "judgeIV_cost_regressions.tex"

    * 2SLS of highway costs on adverse rulings, one table per instrument
    label variable ncases_dem_poc "Cases with a POC Democrat"
    label variable ncases_rep "Cases with a Republican Judge"
    label variable ncases_poc "Cases with a POC Judge"
    // construct lag variables
    foreach v in adverse_rulings_percap share_adverse n_adverse_rulings has_cases n_cases population strictness ncases_dem_poc ncases_rep ncases_poc {
        gen double `v'_lag5 = L5.`v'
        label variable `v'_lag5 "`: variable label `v'' (t-5)"
    }
    foreach v in ncases_dem_poc ncases_rep ncases_poc {
        gen double `v'_lag1 = L.`v'
        label variable `v'_lag1 "`: variable label `v'' (t-1)"
    }

    foreach instrument in dem_poc rep poc {
        local iv ncases_`instrument'
        eststo clear
        foreach lag in "" _lag1 _lag5 {

            eststo iv_percap`lag': ivreg2 spend_per_mile has_cases`lag' n_cases`lag' i.year i.court_id_code (adverse_rulings_percap`lag' = `iv'`lag'), partial(i.year i.court_id_code) cluster(court_id_code)

            eststo iv_share`lag': ivreg2 spend_per_mile n_cases`lag' i.year i.court_id_code (share_adverse`lag' = `iv'`lag'), partial(i.year i.court_id_code) cluster(court_id_code)

            eststo iv_count`lag': ivreg2 spend_per_mile population`lag' n_cases`lag' has_cases`lag' i.year i.court_id_code (n_adverse_rulings`lag' = `iv'`lag'), partial(i.year i.court_id_code) cluster(court_id_code)
        }
        // partial() absorbs the FE, so add the FE rows by hand
        foreach m in iv_percap iv_percap_lag1 iv_percap_lag5 iv_share iv_share_lag1 iv_share_lag5 iv_count iv_count_lag1 iv_count_lag5 {
            estadd local year_fe "X" : `m'
            estadd local circuit_fe "X" : `m'
        }

        esttab iv_percap iv_percap_lag1 iv_percap_lag5 iv_share iv_share_lag1 iv_share_lag5 iv_count iv_count_lag1 iv_count_lag5 using "${tabdir}/judgeIV_2sls_`instrument'.tex", replace ///
            booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
            order(adverse_rulings_percap adverse_rulings_percap_lag1 adverse_rulings_percap_lag5 share_adverse share_adverse_lag1 share_adverse_lag5 n_adverse_rulings n_adverse_rulings_lag1 n_adverse_rulings_lag5) ///
            indicate("Has NEPA Cases = has_cases has_cases_lag1 has_cases_lag5" "Population = population population_lag1 population_lag5" "Num. NEPA Cases = n_cases n_cases_lag1 n_cases_lag5", labels("X" "")) ///
            mtitles("No Lag" "1-Yr Lag" "5-Yr Lag" "No Lag" "1-Yr Lag" "5-Yr Lag" "No Lag" "1-Yr Lag" "5-Yr Lag") ///
            mgroups("Adverse Rulings per 10 Million" "Share of Adverse Rulings" "Number of Adverse Rulings", pattern(1 0 0 1 0 0 1 0 0) span ///
                prefix(\multicolumn{3}{c}{) suffix(})) ///
            prehead("{" "\def\sym#1{\ifmmode^{#1}\else\(^{#1}\)\fi}" "\begin{tabular}{l*{@M}{c}}" "\toprule" ///
                "&\multicolumn{@M}{c}{Highway Cost per Mile}\\") ///
            scalars("year_fe Year FE" "circuit_fe Circuit FE" "N Observations" "widstat First-stage F-stat") ///
            sfmt(%s %s %9.0fc %9.2f) ///
            nonotes
        copy_tab_to_overleaf "judgeIV_2sls_`instrument'.tex"
    }

}

* ==============================================================================
* Judge IV using 6-year periods
* ==============================================================================
if $judgeIV_6yr == 1 {

    use "${data_dir}/Intermediate/Judge IV/judge_iv_case_level.dta", clear

    gen adverse_ruling = anti_dev_score if anti_dev_score != 0.5 // anti-development ruling; missing for mixed and uncoded cases

    * convert case data to 6-yr bins (note Brooks Liscow labels bins by end year)
    gen int period = 1963 + 6 * ceil((year - 1963) / 6)
    assert !(court_id == "ca11" & period <= 1981) // 11th circuit split from the 5th on 10/1/1981

    * panel composition instruments: number of cases in the circuit-period with at least one panel judge with the characteristic
    foreach x in dem_poc rep poc {
        gen byte has_`x' = (count_`x' > 0) if !missing(count_`x')
    }

    * collapse to circuit x period
    collapse (sum) n_adverse_rulings = adverse_ruling ///
        (mean) share_adverse = adverse_ruling ///
        (mean) strictness = c_strict_anti_dev_score ///
        (sum) ncases_dem_poc = has_dem_poc ///
        (sum) ncases_rep = has_rep ///
        (sum) ncases_poc = has_poc ///
        (count) n_cases = case_id, ///
        by(court_id period)
    tab court_id period

    fillin court_id period
    replace n_adverse_rulings = 0 if _fillin
    replace n_cases = 0 if _fillin
    drop _fillin
    drop if court_id == "ca11" & period <= 1981 // 11th circuit did not exist yet

    * set the instruments to 0 in circuit-years with no cases and control for whether there were any cases
    gen byte has_cases = (n_cases > 0)
    foreach v in strictness ncases_dem_poc ncases_rep ncases_poc {
        replace `v' = 0 if !has_cases
    }

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
    replace court_id = "ca5" if inlist(state_abrev, "AL", "FL", "GA") & period <= 1981 // 5th circuit before the 11th circuit split
    collapse (sum) population = pop, by(court_id period) // collapse to circuit and period level
    drop if period < 1970 | period > 1993
    tempfile circuit_period_pop
    save `circuit_period_pop'

    * re-compute spend per mile aggregated to circuit level
    use "${data_dir}/Raw/Brooks Liscow/6yr_In-House_Dataset.dta", clear
    keep state_abrev period_5yr lag_scaled_spending allMiles
    rename period_5yr period // these are the 6-yr bins but named incorrectly in the Brooks Liscow data
    merge m:1 state_abrev using `crosswalk_abrev', keep(match) nogen
    replace court_id = "ca5" if inlist(state_abrev, "AL", "FL", "GA") & period <= 1981 // 5th circuit before the 11th circuit split
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

    gen double adverse_rulings_percap = (n_adverse_rulings / population) * 10000000 // per 10 million

    label variable spend_per_mile "Highway Cost per Mile (\textdollar B, 2016 USD)"
    label variable adverse_rulings_percap "Adverse Rulings per 10 Million"
    label variable share_adverse "Share of Adverse Rulings"
    label variable n_adverse_rulings "Num. Adverse Rulings"
    label variable strictness "Judge Strictness IV"
    label variable has_cases "Any NEPA Cases"
    label variable n_cases "Num. NEPA Cases"
    label variable population "Population"
    label variable ncases_dem_poc "Cases with a POC Democrat"
    label variable ncases_rep "Cases with a Republican Judge"
    label variable ncases_poc "Cases with a POC Judge"

    * construct 1-period lag variables
    foreach v in adverse_rulings_percap share_adverse n_adverse_rulings has_cases n_cases population strictness ncases_dem_poc ncases_rep ncases_poc {
        gen double `v'_lag1 = L.`v'
        label variable `v'_lag1 "`: variable label `v'' (-1 period)"
    }

    eststo clear

    // * strictness IV regressions
    // eststo ols6_t: reg spend_per_mile adverse_rulings_percap has_cases n_cases i.period i.court_id_code, vce(cluster court_id_code)
    // eststo ols6_lag1: reg spend_per_mile adverse_rulings_percap_lag1 has_cases_lag1 n_cases_lag1 i.period i.court_id_code, vce(cluster court_id_code)

    // eststo fs6_t: reg adverse_rulings_percap strictness has_cases n_cases i.period i.court_id_code, vce(cluster court_id_code)
    // eststo fs6_lag1: reg adverse_rulings_percap_lag1 strictness_lag1 has_cases_lag1 n_cases_lag1 i.period i.court_id_code, vce(cluster court_id_code)

    // eststo iv6_t: ivreg2 spend_per_mile has_cases n_cases i.period i.court_id_code (adverse_rulings_percap = strictness), partial(i.period i.court_id_code) cluster(court_id_code)
    // eststo iv6_lag1: ivreg2 spend_per_mile has_cases_lag1 n_cases_lag1 i.period i.court_id_code (adverse_rulings_percap_lag1 = strictness_lag1), partial(i.period i.court_id_code) cluster(court_id_code)
    // // TODO: check syntax for FE/partial() 

    // esttab ols6_t ols6_lag1 fs6_t fs6_lag1 iv6_t iv6_lag1 ///
    //     using "${tabdir}/judgeIV_cost_regressions_6yr.tex", replace ///
    //     booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
    //     drop(_cons) ///
    //     mtitles("\textdollar/Mi" "\textdollar/Mi" ///
    //         "\shortstack{Adverse Rulings\\per 10 Million}" "\shortstack{Adverse Rulings\\per 10 Million (t-1)}" ///
    //         "\textdollar/Mi" "\textdollar/Mi") ///
    //     mgroups("OLS" "First Stage" "IV (2SLS)", pattern(1 0 1 0 1 0) span ///
    //         prefix(\multicolumn{2}{c}{) suffix(})) ///
    //     indicate("Period FE = *.period" "Circuit FE = *.court_id_code", labels("X" "")) ///
    //     scalars("N Observations" "r2_a Adj. R\textsuperscript{2}" "widstat First-stage F-stat") ///
    //     sfmt(%9.0fc %9.3f %9.2f) ///
    //     nonumber ///
    //     nonotes
    // copy_tab_to_overleaf "judgeIV_cost_regressions_6yr.tex"

    * 2SLS of highway costs on adverse rulings, one table per instrument
    foreach instrument in dem_poc rep poc {
        local iv ncases_`instrument'
        eststo clear
        foreach lag in "" _lag1 {

            eststo iv_percap`lag': ivreg2 spend_per_mile n_cases`lag' i.period i.court_id_code (adverse_rulings_percap`lag' = `iv'`lag'), partial(i.period i.court_id_code) cluster(court_id_code)

            eststo iv_share`lag': ivreg2 spend_per_mile n_cases`lag' i.period i.court_id_code (share_adverse`lag' = `iv'`lag'), partial(i.period i.court_id_code) cluster(court_id_code)

            eststo iv_count`lag': ivreg2 spend_per_mile population`lag' n_cases`lag' i.period i.court_id_code (n_adverse_rulings`lag' = `iv'`lag'), partial(i.period i.court_id_code) cluster(court_id_code)
        }
        // partial() absorbs the FE, so add the FE rows by hand
        foreach m in iv_percap iv_percap_lag1 iv_share iv_share_lag1 iv_count iv_count_lag1 {
            estadd local period_fe "X" : `m'
            estadd local circuit_fe "X" : `m'
        }

        esttab iv_percap iv_percap_lag1 iv_share iv_share_lag1 iv_count iv_count_lag1 using "${tabdir}/judgeIV_2sls_`instrument'_6yr.tex", replace ///
            booktabs label se star(* 0.10 ** 0.05 *** 0.01) ///
            order(adverse_rulings_percap adverse_rulings_percap_lag1 share_adverse share_adverse_lag1 n_adverse_rulings n_adverse_rulings_lag1) ///
            indicate("Population = population population_lag1" "Num. NEPA Cases = n_cases n_cases_lag1", labels("X" "")) ///
            mtitles("No Lag" "1-Period Lag" "No Lag" "1-Period Lag" "No Lag" "1-Period Lag") ///
            mgroups("Adverse Rulings per 10 Million" "Share of Adverse Rulings" "Number of Adverse Rulings", pattern(1 0 1 0 1 0) span ///
                prefix(\multicolumn{2}{c}{) suffix(})) ///
            prehead("{" "\def\sym#1{\ifmmode^{#1}\else\(^{#1}\)\fi}" "\begin{tabular}{l*{@M}{c}}" "\toprule" ///
                "&\multicolumn{@M}{c}{Highway Cost per Mile}\\") ///
            scalars("period_fe Period FE" "circuit_fe Circuit FE" "N Observations" "widstat First-stage F-stat") ///
            sfmt(%s %s %9.0fc %9.2f) ///
            nonotes
        copy_tab_to_overleaf "judgeIV_2sls_`instrument'_6yr.tex"
    }

}
