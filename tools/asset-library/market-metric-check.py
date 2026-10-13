"""Transparent synthetic counterexamples, NOT user/company market measurements.

Uses only fixed invented aggregates. No warehouse, advertising or account calls.
These checks verify arithmetic and failure modes, not market causal effects.
"""
from decimal import Decimal as D
import json
import pathlib

ROOT=pathlib.Path('E:/AI/output/embedding-eval-20261005')
cases=[]

def save(name,inputs,outputs,lesson):
    cases.append(dict(name=name,inputs=inputs,outputs=outputs,lesson=lesson,passed=True))

def defined_ratio(numerator,denominator):
    return None if denominator<=0 else numerator/denominator

def same_currency_total(rows):
    if len({row['currency'] for row in rows})!=1:
        raise ValueError('Mixed or missing currency: use an explicit FX policy first')
    return sum(D(str(row['amount'])) for row in rows)

def main():
    # Same currency, mature cohorts and common windows, zero cross-arm duplication.
    a=dict(spend=1000,installs=1000,d7_returners=50,d30_contribution_before_ua=600)
    b=dict(spend=1000,installs=500,d7_returners=150,d30_contribution_before_ua=1200)
    def metrics(x):return dict(cpi=x['spend']/x['installs'],cost_per_d7_returner=x['spend']/x['d7_returners'],d30_contribution_after_ua=x['d30_contribution_before_ua']-x['spend'])
    am,bm=metrics(a),metrics(b)
    assert am['cpi']<bm['cpi'] and am['cost_per_d7_returner']>bm['cost_per_d7_returner'] and am['d30_contribution_after_ua']<bm['d30_contribution_after_ua']
    save('cheap_cpi_can_lose',{'A':a,'B':b},{'A':am,'B':bm},'CPI rank is not retained-user cost or observed contribution rank. D30 is not lifetime; no real asset/product was tested.')

    costs=[D(100),D(900)];revenues=[D(100),D(90)]
    naive=sum(r/c for r,c in zip(revenues,costs))/2
    proper=sum(revenues)/sum(costs)
    assert naive==D('.55') and proper==D('.19')
    save('roas_ratio_of_sums',{'costs':[100,900],'same_window_revenues':[100,90]}, {'naive_mean':float(naive),'proper_total_roas':float(proper)},'For matched windows/cohorts use ratio of totals, equivalent to cost-weighted ROAS. Revenue basis must be consistent.')

    mature,immature,returned=100,100,40
    assert returned/mature==.4 and returned/(mature+immature)==.2
    save('mature_cohort_denominator',{'d7_mature_installs':mature,'d7_immature_installs':immature,'mature_d7_returners':returned},{'wrong_d7':.2,'mature_d7':.4},'Immature cohorts are unobserved, not failed retention. Missing telemetry is another separate status.')

    # A wins within both segments but receives a different user mix.
    ax=[(90,900),(90,100)];bx=[(5,100),(765,900)]
    ar=sum(x[0] for x in ax)/sum(x[1] for x in ax);br=sum(x[0] for x in bx)/sum(x[1] for x in bx)
    ast=sum(n/d for n,d in ax)/2;bst=sum(n/d for n,d in bx)/2
    assert all(an/ad>bn/bd for (an,ad),(bn,bd) in zip(ax,bx)) and ar<br and ast>bst
    save('segment_mix_reversal',{'A_returned_total_by_segment':ax,'B_returned_total_by_segment':bx},{'A_aggregate':ar,'B_aggregate':br,'A_common_50_50_mix':ast,'B_common_50_50_mix':bst},'Standardization separates observed mix from within-segment performance; it does not by itself establish causality. Actual mix still matters for business outcomes.')

    treatment_size=control_size=1000;treated=200;control=160;spend=200;attributed=120
    incremental=(D(treated)/treatment_size-D(control)/control_size)*treatment_size
    assert incremental==40 and D(spend)/incremental==5
    save('attribution_not_incrementality',{'hypothetical_randomized_equal_arms':True,'treatment_size':1000,'control_size':1000,'treatment_conversions':treated,'control_conversions':control,'attributed_conversions':attributed,'spend':spend},{'incremental_conversions_point_estimate':float(incremental),'attributed_cpa':spend/attributed,'incremental_cpa_point_estimate':float(D(spend)/incremental)},'Synthetic arithmetic only: no measured causal lift, confidence interval or significance. Real experiments require valid assignment, uncertainty and interference checks.')

    gross=D(100);refund=D(10);fee=D(27);net=gross-refund-fee;variable=D(8)
    assert net==63 and net-variable==55
    save('gross_net_no_double_deduction',{'hypothetical_gross':100,'refund':10,'explicit_settlement_fee':27,'reported_net_receipts':63,'variable_service_cost':8},{'contribution_before_ua_from_gross':float(gross-refund-fee-variable),'contribution_before_ua_from_net':float(net-variable)},'Explicit fee amounts are invented, not any platform tariff. Already-net receipts must not lose the fee/refund a second time; actual settlement basis controls.')

    # Facts at different grains cannot be joined to raw user rows and summed safely.
    campaign_cost=D(100);users=3
    inflated=campaign_cost*users
    assert inflated==300 and campaign_cost==100
    save('join_fanout',{'campaign_daily_cost':100,'user_rows_same_campaign_day':users},{'wrong_sum_after_user_join':float(inflated),'correct_campaign_cost':float(campaign_cost)},'Aggregate facts to a common supported grain before joins. Do not reconstruct unavailable person-level attribution from aggregate postbacks.')

    assert defined_ratio(0,0) is None and defined_ratio(40,0) is None and defined_ratio(100,-2) is None
    save('undefined_denominators',{'installs':0,'mature_users':0,'incremental_conversions':-2},{'cpi':None,'d7_retention':None,'positive_incremental_cpa':None},'No denominator/no mature cohort means undefined, not zero performance. Nonpositive estimated lift does not define a useful positive acquisition CPA.')

    rows=[{'currency':'USD','amount':100},{'currency':'KRW','amount':100}]
    try:same_currency_total(rows)
    except ValueError:pass
    else:raise AssertionError('Mixed currency was accepted')
    assert same_currency_total([{'currency':'USD','amount':100},{'currency':'USD','amount':50}])==150
    save('currency_boundary',{'mixed_rows':rows},{'mixed_sum':'REJECTED','same_currency_control':150},'Do not sum currencies without a dated documented FX policy. No real FX rate is assumed.')

    first={'as_of':'T30','net_receipts':100};restated={'as_of':'T45','same_cohort_same_revenue_window_refund_adjusted':80}
    assert first['net_receipts']-20==restated['same_cohort_same_revenue_window_refund_adjusted']
    save('late_refund_restatement',{'initial':first,'late_refund_for_original_purchase':20},{'restated':restated,'initial_preserved':first},'Keep as-of versions; late refunds can revise the same purchase cohort. Do not compare unadjusted and adjusted cohorts as if definitions matched.')

    equal_costs=[D(100),D(100)];equal_rev=[D(100),D(10)]
    simple=sum(r/c for r,c in zip(equal_rev,equal_costs))/2;weighted=sum(equal_rev)/sum(equal_costs)
    assert simple==weighted==D('.55')
    save('equal_cost_control',{'costs':[100,100],'revenues':[100,10]},{'both_methods':float(weighted)},'The naive average coincides with the ratio of sums under equal costs; previous counterexample is conditional, not an always-fails claim.')

    control_a=dict(spend=1000,installs=1000,d7_returners=400,d30_contribution_before_ua=2000)
    control_b=dict(spend=1000,installs=500,d7_returners=100,d30_contribution_before_ua=800)
    ma,mb=metrics(control_a),metrics(control_b)
    assert ma['cpi']<mb['cpi'] and ma['cost_per_d7_returner']<mb['cost_per_d7_returner'] and ma['d30_contribution_after_ua']>mb['d30_contribution_after_ua']
    save('cheap_cpi_can_also_win',{'A':control_a,'B':control_b},{'A':ma,'B':mb},'Low CPI can be good when downstream outcomes support it. The lesson is to measure the full outcome, not to penalize cheap acquisition.')

    result={'data_class':'SYNTHETIC_ONLY','date':'2026-10-05','passed':len(cases),'total':len(cases),'real_market_measurements':False,'cases':cases}
    (ROOT/'market-metric-checks.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print('Synthetic metric counterexamples:',len(cases),'/',len(cases),'PASS; real market data: NONE')

if __name__=='__main__':main()
