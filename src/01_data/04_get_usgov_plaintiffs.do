/*==============================================================================
	This script pulls the NEPA cases where the US government is the plaintiff.
    (Code mostly copied from Arpit's 06_nepa_analysis.do)
==============================================================================*/
* Set user
local user = c(username)
if "`user'" == "hl2266" {
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
        display as error "Could not auto-detect location for hl2266; set dropbox/code_dir manually"
    }
}
else if "`user'" == "agupta011" {
    global dropbox "/Users/agupta011/Dropbox/NEPA_court_cases"
}
* add your username and paths here as an else if condition
else {
    display as error "Set your user"
}

global data_dir "${dropbox}/Data"
global output_dir "${dropbox}/Outputs"

* ==============================================================================

insheet using "${data_dir}/Intermediate/Outcome Coding Predictions/courtlistener_metadata_with_LLM_outcomes.csv", clear 
gen int year = real(substr(datefiled, 1, 4))

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

* filter for party1 that starts with "United States"
keep if regexm(party1, "^United States")

* save the data as csv 
export delimited using "${data_dir}/Intermediate/usgov_plaintiffs.csv", replace