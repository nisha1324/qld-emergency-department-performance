-- Star schema for Power BI (Part 5), in DuckDB SQL.
--
-- Run by edperf/star.py, which first registers three views over committed files:
--
--   src_ed_quarterly   data/ed_quarterly.csv            hospital x quarter x triage (1-5 and ALL)
--   src_scorecard      results/scorecard_hospitals.csv  Part 3: level and trend per hospital
--   src_doors          results/doors_hospitals.csv      Part 4: streams and walk-outs per hospital
--   src_comparison     one row: the two quarters Parts 2 to 4 compare (q0, q1)
--
-- The source publishes percentages, not counts. A BI tool can only add counts
-- up correctly, so the fact table turns every percentage back into a head
-- count (attendances x published rate). Each count has a "base" next to it:
-- the attendances of the rows where the rate was published. A rate is always
--
--     sum(count) / sum(its base)
--
-- so a row with no published rate leaves both sides of the division instead
-- of being counted as zero.
--
-- One exception, found in Part 1 (results/SOURCE_PROFILE.md):
-- four quarters publish a zero as `-`, the same symbol as "no data". In those
-- quarters an empty percentage on a row that has attendances is read as 0%.
-- Against the published all-categories figures that reading fits better than
-- dropping the row (see powerbi/CHECKS.md, check 7).

-- Quarters that publish a zero as `-`. "Did not wait" has both a count and a
-- percentage, so it shows the convention: rows with attendances and a count
-- of 0 normally show 0%. In a dash quarter almost none of them do.
create or replace table dash_quarters as
select quarter
from src_ed_quarterly
where attendances > 0 and did_not_wait = 0 and not is_state_total
group by quarter
having count(*) filter (where did_not_wait_pct = 0) < 0.01 * count(*);

-- ---------------------------------------------------------------------------
-- Dimensions
-- ---------------------------------------------------------------------------

create or replace table dim_quarter as
with q as (
    select distinct quarter from src_ed_quarterly
),
parts as (
    select
        quarter,
        cast(substr(quarter, 1, 4) as integer) as calendar_year,
        cast(substr(quarter, 6, 2) as integer) as end_month
    from q
)
select
    calendar_year * 100 + end_month                              as quarter_key,
    quarter                                                      as quarter_code,
    case end_month when 3 then 'Jan-Mar' when 6 then 'Apr-Jun'
                   when 9 then 'Jul-Sep' else 'Oct-Dec' end
        || ' ' || calendar_year                                  as quarter_label,
    case end_month when 3 then 'Jan-Mar' when 6 then 'Apr-Jun'
                   when 9 then 'Jul-Sep' else 'Oct-Dec' end      as quarter_name,
    make_date(calendar_year, end_month - 2, 1)                   as quarter_start,
    calendar_year,
    cast(end_month / 3 as integer)                               as quarter_of_year,
    -- Australian financial year, July to June, named by the year it ends in
    case when end_month >= 9 then calendar_year + 1 else calendar_year end as financial_year,
    cast(row_number() over (order by quarter) as integer)        as quarter_index,
    -- the first quarters were published as whole-number percentages
    not exists (
        select 1 from src_ed_quarterly s
        where s.quarter = parts.quarter
          and s.stay_within_4h_pct <> round(s.stay_within_4h_pct)
    )                                                            as whole_number_rates,
    quarter in (select quarter from dash_quarters)               as zero_published_as_dash,
    -- the two quarters the scorecard compares
    case when quarter = (select q0 from src_comparison) then 'start'
         when quarter = (select q1 from src_comparison) then 'latest' end as comparison_role
from parts;

create or replace table dim_triage as
select * from (values
    (1, '1 Resuscitation', 'Resuscitation',   0, 'Immediately',        '1-2 Most urgent'),
    (2, '2 Emergency',     'Emergency',      10, 'Within 10 minutes',  '1-2 Most urgent'),
    (3, '3 Urgent',        'Urgent',         30, 'Within 30 minutes',  '3 Urgent'),
    (4, '4 Semi-urgent',   'Semi-urgent',    60, 'Within 60 minutes',  '4-5 Less urgent'),
    (5, '5 Non-urgent',    'Non-urgent',    120, 'Within 120 minutes', '4-5 Less urgent')
) as t (triage_key, triage_label, triage_name, recommended_minutes, recommended_wait, urgency_group);

create or replace table dim_hospital as
with latest as (
    select max(quarter) as quarter from src_ed_quarterly
),
span as (
    select
        facility_code,
        min(quarter) as first_quarter,
        max(quarter) as last_quarter,
        cast(count(*) as integer) as quarters_reported
    from src_ed_quarterly
    where triage = 'ALL' and not is_state_total
    group by facility_code
),
named as (
    -- the snapshot carries one name per facility code
    select distinct facility_code, facility_name
    from src_ed_quarterly
    where not is_state_total
)
select
    n.facility_code                                   as hospital_key,
    n.facility_name                                   as hospital_name,
    c.peer_group,
    case c.peer_group when 'large' then 'Large (10,000 or more)'
                      when 'medium' then 'Medium (2,500 to 9,999)'
                      else 'Small (under 2,500)' end  as peer_group_label,
    cast(case c.peer_group when 'large' then 1 when 'medium' then 2 else 3 end as integer)
                                                      as peer_group_sort,
    cast(c.attendances as integer)                    as latest_attendances,
    (select quarter from latest)                      as peer_group_quarter,
    s.first_quarter,
    s.last_quarter,
    s.quarters_reported
from named n
join span s using (facility_code)
join src_scorecard c using (facility_code);

-- ---------------------------------------------------------------------------
-- Fact: hospital x quarter x triage category
-- ---------------------------------------------------------------------------

create or replace table fct_ed_triage_quarter as
with src as (
    select
        s.* replace (
            case when dash and attendances > 0 then coalesce(seen_on_time_pct, 0) else seen_on_time_pct end
                as seen_on_time_pct,
            case when dash and attendances > 0 then coalesce(stay_within_4h_pct, 0) else stay_within_4h_pct end
                as stay_within_4h_pct,
            case when dash and attendances > 0 then coalesce(admitted_pct, 0) else admitted_pct end
                as admitted_pct,
            case when dash and attendances > 0 then coalesce(admitted_within_4h_pct, 0) else admitted_within_4h_pct end
                as admitted_within_4h_pct
        ),
        -- the percentages exactly as published, before the rule above
        seen_on_time_pct        as seen_on_time_pct_raw,
        stay_within_4h_pct      as stay_within_4h_pct_raw,
        admitted_pct            as admitted_pct_raw,
        admitted_within_4h_pct  as admitted_within_4h_pct_raw
    from (
        select *, quarter in (select quarter from dash_quarters) as dash
        from src_ed_quarterly
    ) s
),
base as (
    select
        s.*,
        cast(substr(quarter, 1, 4) as integer) * 100
            + cast(substr(quarter, 6, 2) as integer)      as quarter_key,
        cast(triage as integer)                           as triage_key,
        cast(attendances as double)                       as att,
        -- a category with no attendances has no patients in any group
        case when attendances = 0 then 0.0
             else attendances * admitted_pct / 100 end    as adm
    from src s
    where triage <> 'ALL' and not is_state_total
),
counted as (
    select
        *,
        case when attendances = 0 then 0.0
             else att * seen_on_time_pct / 100 end        as seen,
        case when attendances = 0 then 0.0
             else att * stay_within_4h_pct / 100 end      as stay,
        -- nobody admitted: nobody admitted within 4 hours, whatever is published
        case when adm = 0 then 0.0
             else adm * admitted_within_4h_pct / 100 end  as adm_4h
    from base
)
select
    cast(quarter_key as bigint) * 1000000 + facility_code * 10 + triage_key as ed_row_id,
    quarter_key,
    facility_code                                         as hospital_key,
    triage_key,

    -- published counts
    cast(attendances as integer)                          as attendances,
    cast(did_not_wait as integer)                         as did_not_wait,
    cast(left_after_treatment as integer)                 as left_after_treatment,

    -- seen within the recommended time
    seen                                                  as seen_on_time,
    case when seen is not null then att end               as seen_on_time_base,

    -- whole ED stay within 4 hours
    stay                                                  as stays_within_4h,
    case when stay is not null then att end               as stays_4h_base,

    -- admitted to hospital
    adm                                                   as admitted,
    case when adm is not null then att end                as admitted_base,

    -- the two streams. A row counts only when all three published figures
    -- behind it are there, so the streams add back to the 4-hour stays.
    case when stay is not null and adm_4h is not null then adm end          as stream_admitted,
    case when stay is not null and adm_4h is not null then adm_4h end       as stream_admitted_within_4h,
    case when stay is not null and adm_4h is not null then att - adm end    as stream_not_admitted,
    -- implied, not published: stays within 4 hours minus admitted patients within 4 hours
    case when stay is not null and adm_4h is not null then stay - adm_4h end
                                                          as stream_not_admitted_within_4h,

    -- as published, for reference. Never sum or average these.
    seen_on_time_pct_raw                                  as seen_on_time_pct_published,
    stay_within_4h_pct_raw                                as stay_within_4h_pct_published,
    admitted_pct_raw                                      as admitted_pct_published,
    admitted_within_4h_pct_raw                            as admitted_within_4h_pct_published,
    median_wait_min                                       as median_wait_min_published
from counted;

-- ---------------------------------------------------------------------------
-- Published all-categories rows. A median cannot be rebuilt from categories,
-- so median waits (and the source's own headline rates) live here.
-- ---------------------------------------------------------------------------

create or replace table fct_hospital_quarter_published as
select
    cast(cast(substr(quarter, 1, 4) as integer) * 100
        + cast(substr(quarter, 6, 2) as integer) as bigint) * 100000 + facility_code as hospital_quarter_id,
    cast(substr(quarter, 1, 4) as integer) * 100
        + cast(substr(quarter, 6, 2) as integer)          as quarter_key,
    facility_code                                         as hospital_key,
    cast(attendances as integer)                          as attendances_published,
    median_wait_min                                       as median_wait_min,
    seen_on_time_pct                                      as seen_on_time_pct,
    stay_within_4h_pct                                    as stay_within_4h_pct,
    admitted_pct                                          as admitted_pct,
    admitted_within_4h_pct                                as admitted_within_4h_pct
from src_ed_quarterly
where triage = 'ALL' and not is_state_total;

create or replace table state_published_quarter as
select
    cast(substr(quarter, 1, 4) as integer) * 100
        + cast(substr(quarter, 6, 2) as integer)          as quarter_key,
    cast(attendances as integer)                          as attendances_published,
    median_wait_min                                       as median_wait_min,
    seen_on_time_pct                                      as seen_on_time_pct,
    stay_within_4h_pct                                    as stay_within_4h_pct,
    admitted_pct                                          as admitted_pct,
    admitted_within_4h_pct                                as admitted_within_4h_pct
from src_ed_quarterly
where triage = 'ALL' and is_state_total;

-- ---------------------------------------------------------------------------
-- Scorecard: one row per hospital, the verdicts of Parts 3 and 4 as computed
-- in Python. They depend on a chance test and a two-quarter comparison, so
-- they are carried as columns and not rebuilt in DAX.
-- ---------------------------------------------------------------------------

create or replace table hospital_scorecard as
select
    c.facility_code                       as hospital_key,
    (select q0 from src_comparison)       as comparison_start_quarter,
    (select q1 from src_comparison)       as comparison_latest_quarter,

    -- level: 4-hour rate on the peer group's triage mix, latest quarter
    c.published_1                         as stay_4h_pct_latest_published,
    c.standardised                        as same_mix_rate,
    c.peer_median                         as peer_median_same_mix_rate,
    c.vs_peers                            as same_mix_vs_peer_median,
    c.level                               as level,

    -- trend: within-category change between the two comparison quarters
    c.published_0                         as stay_4h_pct_start_published,
    c.change                              as change_points,
    c.mix                                 as triage_mix_effect,
    c.within                              as within_category_effect,
    c.bar                                 as chance_bar,
    c.trend                               as trend,
    case c.trend when 'slipping' then 1 when 'no clear change' then 2
                 when 'improving' then 3 else 4 end       as trend_sort,
    c.level = 'below peers' and c.trend = 'slipping'      as below_peers_and_slipping,
    c.patients_equivalent                 as patients_equivalent,

    -- Part 4: where the change sits. The four effects add up to change_points.
    d.admission_share                     as admission_share_effect,
    d.admitted                            as admitted_stream_effect,
    coalesce(d.admitted_trend, 'new')     as admitted_stream_trend,
    -- only a slipping or improving verdict can survive (or not survive) rounding
    case when d.admitted_trend in ('slipping', 'improving')
         then d.admitted_robust end       as admitted_verdict_survives_rounding,
    d.not_admitted                        as not_admitted_stream_effect,
    coalesce(d.not_admitted_trend, 'new') as not_admitted_stream_trend,
    case when d.not_admitted_trend in ('slipping', 'improving')
         then d.not_admitted_robust end   as not_admitted_verdict_survives_rounding,
    coalesce(d.pattern, 'new')            as slipping_pattern,

    -- front door
    c.seen_within                         as seen_on_time_within_category_effect,
    c.seen_trend                          as seen_on_time_trend,
    d.median_wait_0                       as median_wait_min_start,
    d.median_wait_1                       as median_wait_min_latest,
    -- median wait went from 0-1 minutes to 5 or more: possibly a recording change
    coalesce(d.wait_step, false)          as wait_step,
    coalesce(d.dnw_trend, 'new')          as did_not_wait_trend,
    coalesce(d.left_trend, 'new')         as left_after_treatment_trend
from src_scorecard c
left join src_doors d using (facility_code);
