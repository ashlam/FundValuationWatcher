import json
import os
import time
import threading
import datetime
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote
from .eastmoney import fetch_fund_estimation, fetch_fund_profile, fetch_fundcode_search, fetch_latest_nav_change
from .db import init_db, get_fund, upsert_fund_profile, upsert_asset_allocations, get_stats, find_fund_code_by_name
from .users_db import (
    init_users_db,
    authenticate,
    create_session,
    delete_session,
    get_user_by_session,
    list_users,
    create_user,
    delete_user,
    list_user_ids,
    count_users,
    get_user_positions_json,
    upsert_user_positions_json,
    delete_user_position_json,
    clear_user_positions_json,
    clear_user_positions_daily,
    upsert_user_positions_daily,
    get_user_positions_daily,
    sum_daily_profit_by_code,
)
from .akshare import fetch_all_funds_basic, fetch_fund_detail_xq

INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>基金实时估值</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
        body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:900px;margin:24px auto;padding:0 16px;color:#666}
        h1{font-size:22px;margin:0 0 12px;color:#666}
        .row{display:flex;gap:8px;margin:12px 0}
        input{flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;color:#666}
        button{padding:8px 12px;border:1px solid #1a73e8;background:#1a73e8;color:#fff;border-radius:6px}
        table{width:100%;border-collapse:collapse;margin-top:12px;color:#666}
        th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;font-size:14px}
        .pos{color:#d93025}
        .neg{color:#0b8f2d}
        .navts{color:#1a73e8}
        .jztoday{color:#0bb8c8}
        .pbtn{padding:2px 6px;border:1px solid #ddd;background:#fff;color:#666;border-radius:999px;font-size:12px;margin-left:6px}
        .pbtn.on{border-color:#1a73e8;color:#1a73e8}
        .muted{color:#888}
        .nav{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #eee;margin-bottom:12px}
        .nav a{color:#1a73e8;text-decoration:none}
</style>
</head>
<body>
<h1>基金实时估值</h1>
<div class="nav">
<a href="/">估值</a>
<a href="/upload-portfolio">个人持仓</a>
<a href="/admin/funds">基金资料维护</a>
<span style="margin-left:auto" id="authLinks"></span>
</div>
<div class="row">
<input id="codes" placeholder="输入基金代码，逗号分隔" />
<button id="refresh">刷新</button>
</div>
<div class="row">
<span class="muted" id="autoRefreshDesc">自动刷新已开启</span>
</div>
<!-- 移除上传入口 -->
<div class="row">
<button id="loadMy">加载我的持仓估值</button>
</div>
<div class="row">
<span>持仓总金额：<strong id="sumAmount">-</strong><button id="toggleSumAmt" class="pbtn" type="button">隐私</button></span>
<span style="margin-left:16px">当日盈亏总金额：<strong id="sumProfit">-</strong><button id="toggleSumProfitMode" class="pbtn" type="button">百分比</button></span>
</div>
<table>
<thead><tr>
<th data-key="fundcode">代码</th>
<th data-key="name">名称</th>
<th data-key="amount">持有金额 <button id="toggleAmt" class="pbtn" type="button">隐私</button></th>
<th data-key="gszzl">估算涨跌幅</th>
<th data-key="profit">当日盈亏（金额）</th>
<th data-key="total_earnings">持有收益金额 <button id="toggleTe" class="pbtn" type="button">隐私</button></th>
<th data-key="return_rate">持有收益率</th>
<th data-key="jzrq">净值日期</th>
<th data-key="gztime">更新时间</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
<script>
const tbody=document.getElementById("tbody")
const codesInput=document.getElementById("codes")
const refreshBtn=document.getElementById("refresh")
const loadMyBtn=document.getElementById("loadMy")
const autoRefreshDesc=document.getElementById("autoRefreshDesc")
const sumAmountEl=document.getElementById("sumAmount")
const sumProfitEl=document.getElementById("sumProfit")
const fmt=v=>v===undefined||v===null?"":v
let portfolioMap={}
let refreshTimer=null
let refreshTimeout=null
let lastItems=[]
let sortKey=null
let sortAsc=true
let hideAmount=false
let hideTotalEarnings=false
let hideSumAmount=false
let showSumProfitPct=false
const toggleSumAmtBtn=document.getElementById("toggleSumAmt")
if(toggleSumAmtBtn){
  toggleSumAmtBtn.addEventListener("click", (e)=>{
    if(e){ e.stopPropagation() }
    hideSumAmount=!hideSumAmount
    toggleSumAmtBtn.className="pbtn"+(hideSumAmount?" on":"")
    toggleSumAmtBtn.textContent=hideSumAmount?"显示":"隐私"
    render(lastItems)
  })
}
const toggleSumProfitModeBtn=document.getElementById("toggleSumProfitMode")
if(toggleSumProfitModeBtn){
  toggleSumProfitModeBtn.addEventListener("click",(e)=>{
    if(e){ e.stopPropagation() }
    showSumProfitPct=!showSumProfitPct
    toggleSumProfitModeBtn.className="pbtn"+(showSumProfitPct?" on":"")
    toggleSumProfitModeBtn.textContent=showSumProfitPct?"金额":"百分比"
    render(lastItems)
  })
}
const toggleAmtBtn=document.getElementById("toggleAmt")
const toggleTeBtn=document.getElementById("toggleTe")
if(toggleAmtBtn){
  toggleAmtBtn.addEventListener("click", (e)=>{
    if(e){ e.stopPropagation() }
    hideAmount=!hideAmount
    toggleAmtBtn.className="pbtn"+(hideAmount?" on":"")
    toggleAmtBtn.textContent=hideAmount?"显示":"隐私"
    render(lastItems)
  })
}
if(toggleTeBtn){
  toggleTeBtn.addEventListener("click", (e)=>{
    if(e){ e.stopPropagation() }
    hideTotalEarnings=!hideTotalEarnings
    toggleTeBtn.className="pbtn"+(hideTotalEarnings?" on":"")
    toggleTeBtn.textContent=hideTotalEarnings?"显示":"隐私"
    render(lastItems)
  })
}
function isTradingHours(d=new Date()){
  const day=d.getDay()
  if(day===0||day===6) return false
  const h=d.getHours(), m=d.getMinutes()
  const t=h*60+m
  const amStart=9*60, amEnd=12*60
  const pmStart=13*60, pmEnd=15*60
  return (t>=amStart && t<amEnd) || (t>=pmStart && t<pmEnd)
}
async function initPortfolio(){
  try{
    const r=await fetch("/api/admin/portfolio",{cache:"no-store"})
    const j=await r.json()
    portfolioMap={}
    for(const it of (j.items||[])){
      const c=(it.code||"").trim()
      const amt=Number(it.amount||0)
      const te=Number(it.total_earnings||0)
      let rr=0
      if(amt!==0){
        rr=(te/amt)*100
      }
      if(c){ portfolioMap[c]={amount:amt, total_earnings:te, return_rate:rr} }
    }
  }catch(e){
    portfolioMap={}
  }
}
async function initRefresh(){
  let sec=55
  try{
    const r=await fetch("/api/config",{cache:"no-store"})
    const j=await r.json()
    sec=Number(j.refresh_interval_seconds||55)
  }catch(e){}
  if(refreshTimer){ clearInterval(refreshTimer); refreshTimer=null }
  if(refreshTimeout){ clearTimeout(refreshTimeout); refreshTimeout=null }
  if(isTradingHours()){
    const ms=Math.max(5000, sec*1000)
    if(autoRefreshDesc){ autoRefreshDesc.textContent=`每${sec}秒自动刷新` }
    refreshTimer=setInterval(load, ms)
  }else{
    const now=new Date()
    const afterClose = (now.getHours()>18 || (now.getHours()===18 && now.getMinutes()>=0)) && now.getHours()<24
    if(afterClose){
      if(autoRefreshDesc){ autoRefreshDesc.textContent=`收盘后每30分钟自动刷新净值` }
      const next=new Date(now)
      next.setSeconds(0,0)
      if(now.getMinutes()<30){
        next.setMinutes(30)
      }else{
        next.setMinutes(0)
        next.setHours(now.getHours()+1)
      }
      const delay=Math.max(1000, next.getTime()-now.getTime())
      refreshTimeout=setTimeout(()=>{
        load()
        refreshTimer=setInterval(load, 30*60*1000)
      }, delay)
    }else{
      if(autoRefreshDesc){ autoRefreshDesc.textContent=`未开盘，自动刷新已暂停` }
      const today18=new Date(now)
      today18.setHours(18,0,0,0)
      if(today18.getTime()>now.getTime()){
        refreshTimeout=setTimeout(initRefresh, Math.max(1000, today18.getTime()-now.getTime()))
      }
    }
  }
}
function render(items){
  tbody.innerHTML=""
  lastItems=Array.isArray(items)?items.slice():[]
  if(sortKey){
    const key=sortKey
    lastItems.sort((a,b)=>{
      const cA=(a.fundcode||"").trim(), cB=(b.fundcode||"").trim()
      const pctOf=x=>((x.daily_pct!==undefined&&x.daily_pct!==null)?Number(x.daily_pct):Number(x.gszzl||0))
      const diffOf=x=>((!isNaN(parseFloat(x.gsz))&&!isNaN(parseFloat(x.dwjz)))?(parseFloat(x.gsz)-parseFloat(x.dwjz)):-99999)
      const pctA=pctOf(a), pctB=pctOf(b)
      const amtA=Number(portfolioMap[cA]?(portfolioMap[cA].amount||0):0), amtB=Number(portfolioMap[cB]?(portfolioMap[cB].amount||0):0)
      const profA=isFinite(amtA)&&isFinite(pctA)?(amtA*pctA/100):0
      const profB=isFinite(amtB)&&isFinite(pctB)?(amtB*pctB/100):0
      const teA=Number(portfolioMap[cA]?(portfolioMap[cA].total_earnings||0):0), teB=Number(portfolioMap[cB]?(portfolioMap[cB].total_earnings||0):0)
      const rrA=Number(portfolioMap[cA]?(portfolioMap[cA].return_rate||0):0), rrB=Number(portfolioMap[cB]?(portfolioMap[cB].return_rate||0):0)
      const valA = key==="amount"?amtA : key==="profit"?profA : key==="total_earnings"?teA : key==="return_rate"?rrA : key==="gszzl"?pctA : key==="fundcode"?String(a.fundcode||"") : key==="name"?String(a.name||"") : key==="jzrq"?String(a.jzrq||"") : key==="gztime"?String(a.gztime||"") : ""
      const valB = key==="amount"?amtB : key==="profit"?profB : key==="total_earnings"?teB : key==="return_rate"?rrB : key==="gszzl"?pctB : key==="fundcode"?String(b.fundcode||"") : key==="name"?String(b.name||"") : key==="jzrq"?String(b.jzrq||"") : key==="gztime"?String(b.gztime||"") : ""
      let cmp=0
      if(typeof valA==="number" && typeof valB==="number"){ cmp = (valA - valB) }
      else { cmp = String(valA).localeCompare(String(valB), "zh-CN", {numeric:true}) }
      return sortAsc?cmp:-cmp
    })
  }
  let sumAmt=0, sumProfit=0
  for(const it of lastItems){
    const pct=(it.daily_pct!==undefined&&it.daily_pct!==null)?Number(it.daily_pct):Number(it.gszzl||0)
    const cls=pct>=0?"pos":"neg"
    const tr=document.createElement("tr")
    const c=(it.fundcode||"").trim()
    const pItem = portfolioMap[c] || {}
    const amt=Number(pItem.amount||0)
    const todayProfit=(isFinite(amt)&&isFinite(pct))?(amt*pct/100):0
    if(isFinite(amt)) sumAmt+=amt
  if(isFinite(todayProfit)) sumProfit+=todayProfit
  
  const te = Number(pItem.total_earnings), rr = Number(pItem.return_rate)
  const teCls = (!hideTotalEarnings && isFinite(te)) ? (te>=0?"pos":"neg") : ""
  const rrCls = isFinite(rr) ? (rr>=0?"pos":"neg") : ""
  const teStr = isFinite(te) ? (te>=0?"+"+te.toFixed(2):te.toFixed(2)) : "-"
  const rrStr = isFinite(rr) ? (rr>=0?"+"+rr.toFixed(2)+"%":rr.toFixed(2)+"%") : "-"

  const amtStr = hideAmount ? "****" : (amt?amt.toFixed(2):"")
        const teShow = hideTotalEarnings ? "****" : teStr
        const timeStr = (it.pct_source==="official" && it.nav_fetched_at) ? fmt(it.nav_fetched_at) : fmt(it.gztime)
        const timeCls = (it.pct_source==="official" && it.nav_fetched_at) ? "navts" : ""
        const todayStr = new Date().toISOString().slice(0,10)
        const jzDate = (it.pct_source==="official" && it.daily_pct_date) ? it.daily_pct_date : it.jzrq
        const jzCls = (String(jzDate||"")===todayStr) ? "jztoday" : ""
        tr.innerHTML=`<td>${fmt(it.fundcode)}</td><td>${fmt(it.name)}</td><td>${amtStr}</td><td class="${cls}">${pct}%</td><td class="${todayProfit>=0?"pos":"neg"}">${amt?todayProfit.toFixed(2):""}</td><td class="${teCls}">${teShow}</td><td class="${rrCls}">${rrStr}</td><td class="${jzCls}">${fmt(jzDate)}</td><td class="${timeCls}">${timeStr}</td>`
        tbody.appendChild(tr)
      }
      if(sumAmountEl) sumAmountEl.textContent = hideSumAmount ? "****" : (sumAmt ? sumAmt.toFixed(2) : "0.00")
      if(sumProfitEl) {
        if(showSumProfitPct && sumAmt>0){
      const pct = (sumProfit/sumAmt)*100
      const pctStr = isFinite(pct) ? ((pct>=0?"+":"")+pct.toFixed(2)+"%") : "0.00%"
      sumProfitEl.textContent = pctStr
    }else{
      sumProfitEl.textContent = (sumProfit>=0?"+":"") + (sumProfit ? sumProfit.toFixed(2) : "0.00")
    }
    sumProfitEl.className = (sumProfit>=0?"pos":"neg")
  }
}
async function load(){
  const raw=codesInput.value.trim()
  if(!raw){ render([]); return }
  const url="/api/funds?codes="+encodeURIComponent(raw)
  try{
    const r=await fetch(url,{cache:"no-store"})
    const j=await r.json()
    render(j.items||[])
  }catch(e){
    render([])
  }
}
async function initAuthLinks(){
  const el=document.getElementById("authLinks")
  if(!el) return
  try{
    const r=await fetch("/api/session",{cache:"no-store"})
    const j=await r.json()
    if(j && j.logged_in){
      const uname=String(j.username||"")
      el.innerHTML = `<span class="muted">用户：${uname}</span> <a href="/switch-user">切换用户</a> <a href="/logout">登出</a>` + (j.is_super?` <a href="/admin/users">管理用户</a>`:"")
    }else{
      el.innerHTML = `<a href="/login">登录</a>`
    }
  }catch(e){}
}
refreshBtn.addEventListener("click",load)
window.addEventListener("load",async ()=>{
  await initAuthLinks()
  await initPortfolio()
  await initRefresh()
  load()
})
document.querySelectorAll("thead th").forEach(th=>{
  th.style.cursor="pointer"
  th.addEventListener("click", ()=>{
    const k=th.getAttribute("data-key")
    if(k){
      if(sortKey===k){ sortAsc=!sortAsc } else { sortKey=k; sortAsc=true }
      render(lastItems)
    }
  })
})
loadMyBtn.addEventListener("click",async ()=>{
  try{
    const r=await fetch("/api/admin/portfolio",{cache:"no-store"})
    const j=await r.json()
    const items=(j.items||[])
    const codes=items.map(it=>it.code).filter(Boolean)
    portfolioMap={}
    for(const it of items){
      const c=(it.code||"").trim()
      const amt=Number(it.amount||0)
      const te=Number(it.total_earnings||0)
      let rr=0
      if(amt!==0){
        rr=(te/amt)*100
      }
      if(c){ portfolioMap[c]={amount:amt, total_earnings:te, return_rate:rr} }
    }
    if(codes.length===0){
      alert("当前个人持仓没有基金代码，无法拉取估值。请在个人持仓页按基金代码新增，或导入包含 code 字段的 JSON。")
      return
    }
    codesInput.value=codes.join(",")
    load()
  }catch(e){
    alert("加载持仓代码失败")
  }
})
</script>
</body>
</html>
"""

UPLOAD_PORTFOLIO_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>上传个人基金持仓</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:900px;margin:24px auto;padding:0 16px;color:#666}
h1{font-size:22px;margin:0 0 12px;color:#666}
.row{display:flex;gap:8px;margin:12px 0}
input,textarea{flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;color:#666}
button{padding:8px 12px;border:1px solid #1a73e8;background:#1a73e8;color:#fff;border-radius:6px}
.muted{color:#888}
.col{display:flex;flex-direction:column;gap:8px}
.preview{display:flex;gap:8px;flex-wrap:wrap}
.preview img{max-width:160px;border:1px solid #eee;border-radius:6px}
table{width:100%;border-collapse:collapse;margin-top:12px;color:#666}
th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;font-size:14px}
.pos{color:#d93025}
.neg{color:#0b8f2d}
.nav{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #eee;margin-bottom:12px}
.nav a{color:#1a73e8;text-decoration:none}
.tabs{display:flex;gap:8px;border-bottom:1px solid #eee;margin-bottom:12px}
.tab{padding:8px 12px;border:1px solid #ddd;border-bottom:none;border-radius:6px 6px 0 0;background:#fff;color:#666}
.tab.active{background:#f5f5f5}
.panel{border:1px solid #eee;border-radius:0 6px 6px 6px;padding:12px}
</style>
</head>
<body>
<h1>上传个人基金持仓</h1>
<div class="nav">
<a href="/">估值</a>
<a href="/upload-portfolio">个人持仓</a>
<a href="/admin/funds">基金资料维护</a>
<span style="margin-left:auto" id="authLinks"></span>
</div>
<div class="col">
<div class="row">
<button id="btnLoadMyPortfolio">我的持仓</button>
</div>
<div>
<div class="tabs">
<button id="tabJson" class="tab active">导入 JSON</button>
<button id="tabTsv" class="tab">导入 TSV</button>
<button id="tabCsv" class="tab">导入 CSV</button>
</div>
<div id="panelJson" class="panel">
<div class="row">
<textarea id="jsonText" rows="6">[{"fund_name":"易方达消费C","amount":1000.0,"earnings_yesterday":12.5,"total_earnings":123.4,"return_rate":1.25,"notes":"示例","code":"110022"}]</textarea>
</div>
<div class="row">
<input id="jsonFile" type="file" accept=".json,application/json" />
<button id="importJsonText">从文本导入</button>
<button id="importJsonFile" style="margin-left:8px">从文件导入</button>
<button id="completeCodes" style="margin-left:8px">补完基金编号</button>
</div>
</div>
<div id="panelTsv" class="panel" style="display:none">
<div class="row">
<textarea id="tsvText" rows="6">fund_name\tamount\tearnings_yesterday\ttotal_earnings\treturn_rate\tnotes
招商量化精选股票C\t4945.27\t-65.19\t235.27\t5.00\t定投</textarea>
</div>
<div class="row">
<input id="tsvFile" type="file" accept=".tsv,text/tab-separated-values" />
<button id="importTsvText">从文本导入</button>
<button id="importTsvFile" style="margin-left:8px">从文件导入</button>
</div>
</div>
<div id="panelCsv" class="panel" style="display:none">
<div class="row">
<textarea id="csvText" rows="6">fund_name,amount,earnings_yesterday,total_earnings,return_rate,notes
招商量化精选股票C,4945.27,-65.19,235.27,5.00,定投</textarea>
</div>
<div class="row">
<input id="csvFile" type="file" accept=".csv,text/csv" />
<button id="importCsvText">从文本导入</button>
<button id="importCsvFile" style="margin-left:8px">从文件导入</button>
</div>
</div>
</div>
<div style="border:1px solid #eee;border-radius:8px;padding:12px;margin-top:12px">
<div class="row"><strong>新增持仓</strong></div>
<div class="row">
<input id="addCode" placeholder="基金代码" />
<input id="addName" placeholder="基金名称（自动填充）" readonly />
</div>
<div class="row">
<input id="addAmount" placeholder="持仓金额" />
<input id="addProfit" placeholder="昨日收益金额" />
<input id="addRate" placeholder="持有收益率(%)" />
</div>
<div class="row">
<button id="addItem">添加</button>
</div>
</div>
<!-- 已移除图片/文本OCR上传与提交 -->
<div class="row">
<span class="muted" id="status"></span>
</div>
<table>
<thead><tr><th style="width:40px"><input id="selectAll" type="checkbox" /></th><th>代码</th><th>基金</th><th>金额</th><th>昨日收益</th><th>持有收益</th></tr></thead>
<tbody id="tbody"></tbody>
</table>
<div class="row" style="justify-content:flex-end">
<button id="btnDeleteSelected" style="background:#b3261e;border-color:#b3261e">批量删除</button>
</div>
</div>
<script>
const statusEl=document.getElementById("status")
const tbody=document.getElementById("tbody")
async function initAuthLinks(){
  const el=document.getElementById("authLinks")
  if(!el) return
  try{
    const r=await fetch("/api/session",{cache:"no-store"})
    const j=await r.json()
    if(j && j.logged_in){
      const uname=String(j.username||"")
      el.innerHTML = `<span class="muted">用户：${uname}</span> <a href="/switch-user">切换用户</a> <a href="/logout">登出</a>` + (j.is_super?` <a href="/admin/users">管理用户</a>`:"")
    }else{
      el.innerHTML = `<a href="/login">登录</a>`
    }
  }catch(e){}
}
const tabJson=document.getElementById("tabJson")
const tabTsv=document.getElementById("tabTsv")
const tabCsv=document.getElementById("tabCsv")
const panelJson=document.getElementById("panelJson")
const panelTsv=document.getElementById("panelTsv")
const panelCsv=document.getElementById("panelCsv")
const jsonText=document.getElementById("jsonText")
const jsonFile=document.getElementById("jsonFile")
const importJsonText=document.getElementById("importJsonText")
const importJsonFile=document.getElementById("importJsonFile")
const completeCodes=document.getElementById("completeCodes")
const tsvText=document.getElementById("tsvText")
const tsvFile=document.getElementById("tsvFile")
const importTsvText=document.getElementById("importTsvText")
const importTsvFile=document.getElementById("importTsvFile")
const csvText=document.getElementById("csvText")
const csvFile=document.getElementById("csvFile")
const importCsvText=document.getElementById("importCsvText")
const importCsvFile=document.getElementById("importCsvFile")
const addCode=document.getElementById("addCode")
const addName=document.getElementById("addName")
const addAmount=document.getElementById("addAmount")
const btnLoadMyPortfolio=document.getElementById("btnLoadMyPortfolio")
const btnDeleteSelected=document.getElementById("btnDeleteSelected")
const selectAll=document.getElementById("selectAll")
let selectedCodes = new Set()
if(btnLoadMyPortfolio){
  btnLoadMyPortfolio.addEventListener("click", loadList)
}
if(selectAll){
  selectAll.addEventListener("change", ()=>{
    const checked = !!selectAll.checked
    selectedCodes = new Set()
    tbody.querySelectorAll("input.sel").forEach(cb=>{
      cb.checked = checked
      const code = cb.getAttribute("data-code") || ""
      if(checked && code) selectedCodes.add(code)
    })
  })
}
if(btnDeleteSelected){
  btnDeleteSelected.addEventListener("click", async ()=>{
    const codes = Array.from(selectedCodes.values()).filter(Boolean)
    if(codes.length===0){ alert("请先勾选要删除的持仓"); return }
    if(!confirm("确定批量删除已勾选的 "+codes.length+" 条持仓吗？")) return
    try{
      const r = await fetch("/api/admin/portfolio/delete_batch", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({codes})})
      const j = await r.json()
      if(r.ok && j.ok){
        selectedCodes = new Set()
        if(selectAll) selectAll.checked = false
        loadList()
      }else{
        alert(j.error || "批量删除失败")
      }
    }catch(e){
      alert("批量删除失败")
    }
  })
}
const addProfit=document.getElementById("addProfit")
const addRate=document.getElementById("addRate")
const addItem=document.getElementById("addItem")
// 已移除图片预览
function render(items){
  tbody.innerHTML=""
  for(const it of items||[]){
    const tr=document.createElement("tr")
    const te=Number(it.total_earnings)
    const teCls = isFinite(te) ? (te>=0?"pos":"neg") : ""
    const code = (it.code||"")
    const checked = selectedCodes.has(code)
    tr.innerHTML=`<td><input class="sel" type="checkbox" data-code="${code}" ${checked?"checked":""} /></td><td>${code}</td><td>${it.fund_name||""}</td><td>${it.amount??""}</td><td>${it.earnings_yesterday??""}</td><td class="${teCls}">${it.total_earnings??""}</td>
    <td>
      <button class="edit" data-code="${it.code||""}">修改</button>
      <button class="del" data-code="${it.code||""}">删除</button>
    </td>`
    tbody.appendChild(tr)
  }
  for(const cb of tbody.querySelectorAll("input.sel")){
    cb.addEventListener("change", ()=>{
      const code = cb.getAttribute("data-code") || ""
      if(!code) return
      if(cb.checked) selectedCodes.add(code)
      else selectedCodes.delete(code)
      if(selectAll){
        const all = Array.from(tbody.querySelectorAll("input.sel"))
        selectAll.checked = (all.length>0 && all.every(x=>x.checked))
      }
    })
  }
  for(const btn of tbody.querySelectorAll("button.edit")){
    btn.addEventListener("click",()=>{
      const code=btn.getAttribute("data-code")
      const tr=btn.closest("tr")
      const tds=tr.querySelectorAll("td")
      const codeInput=document.createElement("input")
      codeInput.value=tds[1].textContent||""
      const amtInput=document.createElement("input")
      amtInput.value=tds[3].textContent||""
      const eyInput=document.createElement("input")
      eyInput.value=tds[4].textContent||""
      const teInput=document.createElement("input")
      teInput.value=tds[5].textContent||""
      tds[1].innerHTML=""
      tds[1].appendChild(codeInput)
      tds[3].innerHTML=""
      tds[3].appendChild(amtInput)
      tds[4].innerHTML=""
      tds[4].appendChild(eyInput)
      tds[5].innerHTML=""
      tds[5].appendChild(teInput)
      btn.textContent="保存"
      btn.onclick=async ()=>{
        if(!code){ alert("请先补完基金编号"); return }
        const newCode = codeInput.value.trim()
        if(!newCode){ alert("基金代码不能为空"); return }
        const body=new URLSearchParams()
        body.set("code", code)
        if(newCode && newCode!==code) body.set("new_code", newCode)
        if(amtInput.value.trim()) body.set("amount", amtInput.value.trim())
        if(eyInput.value.trim()) body.set("earnings_yesterday", eyInput.value.trim())
        if(teInput.value.trim()) body.set("total_earnings", teInput.value.trim())
        try{
          const r = await fetch("/api/admin/portfolio/update",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.toString()})
          const j = await r.json()
          if(r.ok && j.ok){
            loadList()
          }else{
            alert(j.error || "保存失败")
          }
        }catch(e){
          alert("保存失败")
        }
      }
    })
  }
  for(const btn of tbody.querySelectorAll("button.del")){
    btn.addEventListener("click",async ()=>{
      const code=btn.getAttribute("data-code")
      const body=new URLSearchParams()
      body.set("code", code)
      await fetch("/api/admin/portfolio/delete",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.toString()})
      loadList()
    })
  }
}
async function loadList(){
  try{
    const r=await fetch("/api/admin/portfolio",{cache:"no-store"})
    const j=await r.json()
    render(j.items||[])
  }catch(e){
    render([])
  }
}
addCode.addEventListener("blur",async ()=>{
  const c=addCode.value.trim()
  if(!c){ addName.value=""; return }
  try{
    const r=await fetch("/api/admin/fund/local?code="+encodeURIComponent(c),{cache:"no-store"})
    if(r.ok){
      const j=await r.json()
      addName.value=j.name||""
    }else{
      addName.value=""
      statusEl.textContent="基金代码不存在"
    }
  }catch(e){
    addName.value=""
  }
})
addItem.addEventListener("click",async ()=>{
  const c=addCode.value.trim()
  if(!c){ statusEl.textContent="请输入基金代码"; return }
  const body=new URLSearchParams()
  body.set("code", c)
  body.set("fund_name", addName.value.trim())
  if(addAmount.value.trim()) body.set("amount", addAmount.value.trim())
  if(addProfit.value.trim()) body.set("earnings_yesterday", addProfit.value.trim())
  if(addRate.value.trim()) body.set("return_rate", addRate.value.trim())
  await fetch("/api/admin/portfolio/add",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.toString()})
  addCode.value=""; addName.value=""; addAmount.value=""; addProfit.value=""; addRate.value="";
  loadList()
})
function showTab(name){
  panelJson.style.display = name==="json" ? "" : "none"
  panelTsv.style.display = name==="tsv" ? "" : "none"
  panelCsv.style.display = name==="csv" ? "" : "none"
  tabJson.className = "tab" + (name==="json" ? " active" : "")
  tabTsv.className = "tab" + (name==="tsv" ? " active" : "")
  tabCsv.className = "tab" + (name==="csv" ? " active" : "")
}
tabJson.addEventListener("click",()=>showTab("json"))
tabTsv.addEventListener("click",()=>showTab("tsv"))
tabCsv.addEventListener("click",()=>showTab("csv"))
importJsonText.addEventListener("click",async ()=>{
  let payload={}
  try{ payload=JSON.parse(jsonText.value.trim()) }catch(e){ statusEl.textContent="JSON 格式错误"; return }
  if(!Array.isArray(payload)){ statusEl.textContent="JSON 需为数组"; return }
  const r=await fetch("/api/admin/portfolio/json",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})
  const j=await r.json()
  const nf=(j.not_found||[])
  statusEl.textContent=`导入 ${j.count||0} 条${nf.length?`；未找到：${nf.join("、")}`:""}`
  loadList()
})
importJsonFile.addEventListener("click",async ()=>{
  try{
    const txt=await readFileText(jsonFile)
    let payload={}
    try{ payload=JSON.parse(String(txt||"")) }catch(e){ statusEl.textContent="JSON 文件格式错误"; return }
    if(!Array.isArray(payload)){ statusEl.textContent="JSON 需为数组"; return }
    const r=await fetch("/api/admin/portfolio/json",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})
    const j=await r.json()
    statusEl.textContent=`导入 ${j.count||0} 条`
    loadList()
  }catch(e){
    statusEl.textContent="读取 JSON 文件失败"
  }
})
function parseDelimited(text, delim){
  const t=(text||"").split(String.fromCharCode(13)).join("")
  const lines=t.split(String.fromCharCode(10)).filter(x=>x.trim().length>0)
  if(lines.length===0) return []
  const header=lines[0].split(delim).map(x=>x.trim())
  const idx=(name)=>{const i=header.indexOf(name);return i>=0?i:null}
  const iFund=idx("fund_name")
  const iAmt=idx("amount")
  const iEY=idx("earnings_yesterday")
  const iTE=idx("total_earnings")
  const iRR=idx("return_rate")
  const iNotes=idx("notes")
  const out=[]
  for(let k=1;k<lines.length;k++){
    const cols=lines[k].split(delim)
    const obj={
      fund_name: iFund!=null ? (cols[iFund]||"").trim() : "",
      amount: iAmt!=null ? Number((cols[iAmt]||"").trim()||0) : undefined,
      earnings_yesterday: iEY!=null ? Number((cols[iEY]||"").trim()||0) : undefined,
      total_earnings: iTE!=null ? Number((cols[iTE]||"").trim()||0) : undefined,
      return_rate: iRR!=null ? Number((cols[iRR]||"").trim()||0) : undefined,
      notes: iNotes!=null ? (cols[iNotes]||"").trim() : undefined
    }
    if(obj.fund_name){ out.push(obj) }
  }
  return out
}
function parseCsv(text){
  const t=(text||"").split(String.fromCharCode(13)).join("")
  const lines=t.split(String.fromCharCode(10)).filter(x=>x.trim().length>0)
  if(lines.length===0) return []
  const parseLine=(s)=>{
    const out=[]; let cur=""; let q=false
    for(let i=0;i<s.length;i++){
      const ch=s[i]
      if(ch==='\"'){
        if(q && s[i+1]==='\"'){ cur+='\"'; i++ } else { q=!q }
      }else if(ch===',' && !q){
        out.push(cur); cur=""
      }else{
        cur+=ch
      }
    }
    out.push(cur)
    return out.map(x=>x.trim())
  }
  const header=parseLine(lines[0])
  const idx=(name)=>{const i=header.indexOf(name);return i>=0?i:null}
  const iFund=idx("fund_name")
  const iAmt=idx("amount")
  const iEY=idx("earnings_yesterday")
  const iTE=idx("total_earnings")
  const iRR=idx("return_rate")
  const iNotes=idx("notes")
  const out=[]
  for(let k=1;k<lines.length;k++){
    const cols=parseLine(lines[k])
    const obj={
      fund_name: iFund!=null ? (cols[iFund]||"").trim() : "",
      amount: iAmt!=null ? Number((cols[iAmt]||"").trim()||0) : undefined,
      earnings_yesterday: iEY!=null ? Number((cols[iEY]||"").trim()||0) : undefined,
      total_earnings: iTE!=null ? Number((cols[iTE]||"").trim()||0) : undefined,
      return_rate: iRR!=null ? Number((cols[iRR]||"").trim()||0) : undefined,
      notes: iNotes!=null ? (cols[iNotes]||"").trim() : undefined
    }
    if(obj.fund_name){ out.push(obj) }
  }
  return out
}
function readFileText(input){
  return new Promise((resolve,reject)=>{
    const f=input.files && input.files[0]
    if(!f){ reject(new Error("no_file")); return }
    const fr=new FileReader()
    fr.onload=()=>resolve(String(fr.result||""))
    fr.onerror=()=>reject(new Error("read_error"))
    fr.readAsText(f, "utf-8")
  })
}
importTsvText.addEventListener("click",async ()=>{
  try{
    const items=parseDelimited(tsvText.value||"", String.fromCharCode(9))
    if(items.length===0){ statusEl.textContent="TSV 文本为空"; return }
    const r=await fetch("/api/admin/portfolio/json",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(items)})
    const j=await r.json()
    statusEl.textContent=`TSV 导入 ${j.count||0} 条`
    loadList()
  }catch(e){
    statusEl.textContent="TSV 文本导入失败"
  }
})
importTsvFile.addEventListener("click",async ()=>{
  try{
    const txt=await readFileText(tsvFile)
    const items=parseDelimited(txt, String.fromCharCode(9))
    if(items.length===0){ statusEl.textContent="TSV 内容为空"; return }
    const r=await fetch("/api/admin/portfolio/json",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(items)})
    const j=await r.json()
    statusEl.textContent=`TSV 导入 ${j.count||0} 条`
    loadList()
  }catch(e){
    statusEl.textContent="TSV 导入失败"
  }
})
importCsvText.addEventListener("click",async ()=>{
  try{
    const items=parseCsv(csvText.value||"")
    if(items.length===0){ statusEl.textContent="CSV 文本为空"; return }
    const r=await fetch("/api/admin/portfolio/json",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(items)})
    const j=await r.json()
    statusEl.textContent=`CSV 导入 ${j.count||0} 条`
    loadList()
  }catch(e){
    statusEl.textContent="CSV 文本导入失败"
  }
})
importCsvFile.addEventListener("click",async ()=>{
  try{
    const txt=await readFileText(csvFile)
    const items=parseCsv(txt)
    if(items.length===0){ statusEl.textContent="CSV 内容为空"; return }
    const r=await fetch("/api/admin/portfolio/json",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(items)})
    const j=await r.json()
    statusEl.textContent=`CSV 导入 ${j.count||0} 条`
    loadList()
  }catch(e){
    statusEl.textContent="CSV 导入失败"
  }
})
completeCodes.addEventListener("click",async ()=>{
  let payload={}
  try{ payload=JSON.parse(jsonText.value.trim()) }catch(e){ statusEl.textContent="JSON 格式错误"; return }
  if(!Array.isArray(payload)){ statusEl.textContent="JSON 需为数组"; return }
  const r=await fetch("/api/admin/portfolio/complete_codes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})
  const j=await r.json()
  if(j.items){
    jsonText.value=JSON.stringify(j.items, null, 2)
    const nf=(j.not_found||[])
    statusEl.textContent=`已补完 ${j.completed||0} 条基金代码${nf.length?`；未找到：${nf.join("、")}`:""}`
  }else{
    statusEl.textContent="未能补完基金代码"
  }
})
// 已移除OCR提交
initAuthLinks()
loadList()
</script>
</body>
</html>
"""
UPLOAD_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>上传截图同步持仓</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:900px;margin:24px auto;padding:0 16px;color:#666}
h1{font-size:22px;margin:0 0 12px;color:#666}
.row{display:flex;gap:8px;margin:12px 0}
input,textarea{flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;color:#666}
button{padding:8px 12px;border:1px solid #1a73e8;background:#1a73e8;color:#fff;border-radius:6px}
.muted{color:#888}
.col{display:flex;flex-direction:column;gap:8px}
.preview{display:flex;gap:8px;flex-wrap:wrap}
.preview img{max-width:160px;border:1px solid #eee;border-radius:6px}
table{width:100%;border-collapse:collapse;margin-top:12px;color:#666}
th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;font-size:14px}
</style>
</head>
<body>
<h1>上传截图同步持仓</h1>
<div class="row">
<a href="/">返回首页</a>
</div>
<div class="col">
<div class="row">
<input id="code" placeholder="基金代码，如 110022" />
<input id="reportDate" placeholder="报告日期 YYYY-MM-DD，可留空自动识别" />
</div>
<div class="row">
<input id="images" type="file" multiple accept="image/*" />
</div>
<div class="preview" id="preview"></div>
<div class="row">
<textarea id="text" rows="6" placeholder="可选：直接粘贴持仓文本，每行如：贵州茅台 9.50%"></textarea>
</div>
<div class="row">
<label style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="commit" /><span>入库</span></label>
</div>
<div class="row">
<button id="submit">提交分析（不入库）</button>
</div>
<div class="row">
<span class="muted" id="status"></span>
</div>
<table>
<thead><tr><th>名称</th><th>占比(%)</th></tr></thead>
<tbody id="tbody"></tbody>
</table>
</div>
<script>
const code=document.getElementById("code")
const reportDate=document.getElementById("reportDate")
const images=document.getElementById("images")
const text=document.getElementById("text")
const submit=document.getElementById("submit")
const statusEl=document.getElementById("status")
const tbody=document.getElementById("tbody")
const preview=document.getElementById("preview")
const commitInput=document.getElementById("commit")
images.addEventListener("change",()=>{
  preview.innerHTML=""
  for(const f of images.files){
    const url=URL.createObjectURL(f)
    const img=document.createElement("img")
    img.src=url
    preview.appendChild(img)
  }
})
function render(items){
  tbody.innerHTML=""
  for(const it of items||[]){
    const tr=document.createElement("tr")
    tr.innerHTML=`<td>${it.name||""}</td><td>${it.weight??""}</td>`
    tbody.appendChild(tr)
  }
}
submit.addEventListener("click",async ()=>{
  const c=code.value.trim()
  if(!c){ statusEl.textContent="请输入基金代码"; return }
  const fd=new FormData()
  const t=text.value.trim()
  if(t){ fd.append("text", t) }
  for(const f of images.files){ fd.append("images", f) }
  statusEl.textContent="正在分析..."
  const q=new URLSearchParams()
  q.set("code", c)
  const rd=reportDate.value.trim()
  if(rd){ q.set("report_date", rd) }
  if(commitInput.checked){ q.set("commit", "1") }
  try{
    const r=await fetch("/api/admin/holdings/ocr?"+q.toString(),{method:"POST",body:fd})
    const j=await r.json()
    statusEl.textContent=(j.committed?`已入库 ${j.count||0} 条，报告日期 ${j.report_date||""}`:`预览 ${j.count||0} 条，报告日期 ${j.report_date||""}`)
    render(j.items||[])
  }catch(e){
    statusEl.textContent="分析失败"
    render([])
  }
})
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200, extra_headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in (extra_headers or {}).items():
                self.send_header(str(k), str(v))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html, status=200, extra_headers=None):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in (extra_headers or {}).items():
                self.send_header(str(k), str(v))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return

    def _parse_cookies(self):
        raw = self.headers.get("Cookie") or ""
        out = {}
        for part in raw.split(";"):
            s = part.strip()
            if not s or "=" not in s:
                continue
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
        return out

    def _current_user(self):
        ck = self._parse_cookies()
        tok = ck.get("fw_session")
        if not tok:
            return None
        return get_user_by_session(tok)

    def _set_session_cookie_header(self, token):
        if token:
            return f"fw_session={token}; Path=/; HttpOnly; SameSite=Lax"
        return "fw_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"

    def _redirect(self, location, *, set_cookie_header=None):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        if set_cookie_header:
            self.send_header("Set-Cookie", set_cookie_header)
        self.end_headers()

    def _require_login_page(self, next_url):
        u = self._current_user()
        if u:
            return u
        q = quote(str(next_url or "/"), safe="")
        self._send_html(
            "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>未登录</title><style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:720px;margin:24px auto;padding:0 16px;color:#666}"
            "a{color:#1a73e8;text-decoration:none}</style></head><body>"
            "<h2>未登录</h2><p>需要先登录才能访问此页面。</p>"
            f"<p><a href='/login?next={q}'>去登录</a></p>"
            "</body></html>"
        )
        return None

    def _require_login_api(self):
        u = self._current_user()
        if u:
            return u
        self._send_json({"ok": False, "error": "not_logged_in"}, status=401)
        return None

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/api/session":
            u = self._current_user()
            if not u:
                self._send_json({"ok": True, "logged_in": False})
                return
            self._send_json({"ok": True, "logged_in": True, "username": u.get("username"), "is_super": bool(u.get("is_super"))})
            return
        if p.path == "/switch-user":
            ck = self._parse_cookies()
            tok = ck.get("fw_session")
            if tok:
                delete_session(tok)
            self._redirect("/login", set_cookie_header=self._set_session_cookie_header(None))
            return
        if p.path == "/login":
            q = parse_qs(p.query or "")
            nxt = unquote((q.get("next") or ["/"])[0] or "/")
            cur = self._current_user()
            cur_user = (cur or {}).get("username") if cur else None
            cur_block = f"<div class='row'><span class='muted'>当前已登录：{cur_user}（如要切换用户，请先 <a href=\"/switch-user\">登出</a>）</span></div>" if cur_user else ""
            try:
                uc = count_users(include_admin=True)
            except Exception:
                uc = 0
            cur_block = (cur_block or "") + f"<div class='row'><span class='muted'>当前注册用户数：{uc}</span></div>"
            html = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>登录</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:720px;margin:24px auto;padding:0 16px;color:#666}
h1{font-size:22px;margin:0 0 12px;color:#666}
.row{display:flex;gap:8px;margin:12px 0}
input{flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;color:#666}
button{padding:8px 12px;border:1px solid #1a73e8;background:#1a73e8;color:#fff;border-radius:6px}
.muted{color:#888}
a{color:#1a73e8;text-decoration:none}
</style>
</head>
<body>
<h1>登录</h1>
%s
<div class="row"><input id="u" placeholder="用户名" /></div>
<div class="row"><input id="p" placeholder="密码" type="password" /></div>
<div class="row"><button id="btn">登录</button></div>
<div class="row"><span id="msg" class="muted"></span></div>
<div class="row"><span class="muted">默认超级用户：admin/admin</span></div>
<script>
const nextUrl=%s
document.getElementById("btn").addEventListener("click", async ()=>{
  const u=document.getElementById("u").value.trim()
  const p=document.getElementById("p").value
  const msg=document.getElementById("msg")
  if(!u||!p){ msg.textContent="请输入用户名和密码"; return }
  try{
    const body=new URLSearchParams()
    body.set("username", u)
    body.set("password", p)
    const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.toString()})
    const j=await r.json()
    if(r.status===200 && j.ok){
      location.href=nextUrl||"/"
    }else{
      msg.textContent=j.error||"登录失败"
    }
  }catch(e){
    msg.textContent="登录失败"
  }
})
</script>
</body>
</html>
""" % (cur_block, json.dumps(nxt))
            self._send_html(html)
            return
        if p.path == "/logout":
            ck = self._parse_cookies()
            tok = ck.get("fw_session")
            if tok:
                delete_session(tok)
            self._redirect("/login", set_cookie_header=self._set_session_cookie_header(None))
            return
        if p.path == "/":
            u = self._require_login_page("/")
            if not u:
                return
            self._send_html(INDEX_HTML)
            return
        if p.path == "/api/config":
            try:
                cfg = get_config()
            except Exception:
                cfg = {"refresh_interval_seconds": 55}
            self._send_json(cfg)
            return
        if p.path == "/upload-portfolio":
            u = self._require_login_page("/upload-portfolio")
            if not u:
                return
            self._send_html(UPLOAD_PORTFOLIO_HTML)
            return
        if p.path == "/admin/funds":
            html = """<!doctype html><html><head><meta charset="utf-8"><title>基金资料维护</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:900px;margin:24px auto;padding:0 16px;color:#666}.nav{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #eee;margin-bottom:12px}.nav a{color:#1a73e8;text-decoration:none}.row{display:flex;gap:8px;margin:12px 0}input,textarea{flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;color:#666}button{padding:8px 12px;border:1px solid #1a73e8;background:#1a73e8;color:#fff;border-radius:6px}.muted{color:#888}.progress{width:100%;height:8px;background:#eee;border-radius:6px}.bar{height:100%;background:#1a73e8;width:0%;border-radius:6px}</style></head><body><h1>基金资料维护</h1><div class="nav"><a href="/">估值</a><a href="/upload-portfolio">个人持仓</a><a href="/admin/funds">基金资料维护</a></div><div class="row"><strong>手动录入</strong></div><div class="row"><input id="code" placeholder="基金代码"><input id="name" placeholder="基金名称"><input id="type" placeholder="类型"><input id="company" placeholder="公司"><input id="managers" placeholder="经理（逗号分隔）"></div><div class="row"><button id="save">保存到本地</button></div><div class="row"><strong>从网上获取并保存</strong></div><div class="row"><input id="fetchCode" placeholder="基金代码"><button id="fetchSave">获取并保存</button></div><div class="row"><strong>一键补充/更新（EastMoney基金代码库）</strong></div><div class="row"><input id="emLimit" placeholder="每批条数（默认500）"><input id="emOffset" placeholder="起始offset（默认0）"><button id="emIngest">批量导入</button></div><div class="row"><div class="progress"><div id="emBar" class="bar"></div></div></div><div class="row"><span id="status" class="muted"></span></div><script>const statusEl=document.getElementById("status");document.getElementById("save").addEventListener("click",async()=>{const body=new URLSearchParams();const code=document.getElementById("code").value.trim();if(!code){statusEl.textContent="请输入基金代码";return}body.set("code",code);body.set("name",document.getElementById("name").value.trim());body.set("type",document.getElementById("type").value.trim());body.set("company",document.getElementById("company").value.trim());body.set("managers",document.getElementById("managers").value.trim());const r=await fetch("/api/admin/fund/save",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.toString()});const j=await r.json();statusEl.textContent=j.ok?"已保存":"保存失败"});document.getElementById("fetchSave").addEventListener("click",async()=>{const code=document.getElementById("fetchCode").value.trim();if(!code){statusEl.textContent="请输入基金代码";return}const r=await fetch("/api/admin/fund/fetch_save?code="+encodeURIComponent(code));const j=await r.json();statusEl.textContent=j.ok?("已获取并保存："+(j.profile&&j.profile.name||"")):"获取失败"});document.getElementById("emIngest").addEventListener("click",async()=>{const limRaw=document.getElementById("emLimit").value.trim();const offRaw=document.getElementById("emOffset").value.trim();const chunk=limRaw?parseInt(limRaw,10):500;let offset=offRaw?parseInt(offRaw,10):0;let total=0;let done=0;const bar=document.getElementById("emBar");statusEl.textContent="准备中...";try{const meta=await fetch("/api/admin/eastmoney/fundcodes/meta");if(meta.ok){const j=await meta.json();total=j.total||0}}catch(e){}if(!total){statusEl.textContent="无法获取总量，改为单次导入";const q=new URLSearchParams();if(limRaw) q.set("limit",limRaw);if(offRaw) q.set("offset",offRaw);const r=await fetch("/api/admin/eastmoney/fundcodes/ingest?"+q.toString());const j=await r.json();statusEl.textContent=j.ok?`已导入 ${j.count||0} 条`:"导入失败";bar.style.width="100%";return}statusEl.textContent=`开始导入，共 ${total} 条`;while(offset<total){const q=new URLSearchParams();q.set("limit", String(chunk));q.set("offset", String(offset));const r=await fetch("/api/admin/eastmoney/fundcodes/ingest?"+q.toString());const j=await r.json();if(!j.ok){statusEl.textContent="导入失败";break}done+=j.count||0;offset+=chunk;const pct=Math.min(100, Math.floor(done*100/total));bar.style.width=pct+"%";statusEl.textContent=`已导入 ${done}/${total}`;}if(offset>=total){bar.style.width="100%";statusEl.textContent=`完成，共导入 ${done} 条`;}});</script></body></html>"""
            self._send_html(html)
            return
        if p.path == "/api/admin/ingest":
            q = parse_qs(p.query or "")
            raw = (q.get("codes") or [""])[0].strip()
            if not raw:
                self._send_json({"ok": True})
                return
            codes = [x.strip() for x in raw.split(",") if x.strip()]
            for code in codes:
                prof = fetch_fund_profile(code)
                if prof:
                    upsert_fund_profile(code, prof.get("name"), prof.get("type"), prof.get("company"), prof.get("managers"))
                allocs = None
                try:
                    from .eastmoney import fetch_asset_allocation
                    allocs = fetch_asset_allocation(code)
                except Exception:
                    allocs = None
                if allocs:
                    upsert_asset_allocations(code, allocs)
            self._send_json({"ok": True, "count": len(codes)})
            return
        if p.path == "/api/admin/dbinfo":
            self._send_json(get_stats())
            return
        if p.path == "/api/admin/akshare/ingest":
            q = parse_qs(p.query or "")
            try:
                limit = int((q.get("limit") or ["0"])[0].strip() or "0")
            except Exception:
                limit = 0
            try:
                offset = int((q.get("offset") or ["0"])[0].strip() or "0")
            except Exception:
                offset = 0
            detail = ((q.get("detail") or ["0"])[0].strip().lower() in ("1","true","yes"))
            lst = fetch_all_funds_basic()
            if not lst:
                self._send_json({"ok": False, "error": "akshare_unavailable_or_empty"})
                return
            if offset > 0:
                lst = lst[offset:]
            if limit > 0:
                lst = lst[:limit]
            cnt = 0
            for it in lst:
                code = str(it.get("code") or "").strip()
                if not code:
                    continue
                name = it.get("name")
                type_ = it.get("type")
                company = None
                managers = None
                if detail:
                    det = fetch_fund_detail_xq(code)
                    if det:
                        name = det.get("name") or name
                        type_ = det.get("type") or type_
                        company = det.get("company")
                        managers = det.get("managers")
                upsert_fund_profile(code, name, type_, company, managers)
                cnt += 1
            self._send_json({"ok": True, "count": cnt, "offset": offset, "limit": limit, "detail": detail})
            return
        if p.path == "/api/admin/eastmoney/fundcodes/ingest":
            q = parse_qs(p.query or "")
            try:
                limit = int((q.get("limit") or ["0"])[0].strip() or "0")
            except Exception:
                limit = 0
            try:
                offset = int((q.get("offset") or ["0"])[0].strip() or "0")
            except Exception:
                offset = 0
            lst = fetch_fundcode_search()
            if not lst:
                self._send_json({"ok": False, "error": "eastmoney_fundcode_unavailable_or_empty"})
                return
            if offset > 0:
                lst = lst[offset:]
            if limit > 0:
                lst = lst[:limit]
            cnt = 0
            for it in lst:
                code = str(it.get("code") or "").strip()
                if not code:
                    continue
                name = it.get("name")
                type_ = it.get("type")
                upsert_fund_profile(code, name, type_, None, None)
                cnt += 1
            self._send_json({"ok": True, "count": cnt, "offset": offset, "limit": limit})
            return
        if p.path == "/api/admin/eastmoney/fundcodes/meta":
            lst = fetch_fundcode_search()
            total = len(lst or [])
            self._send_json({"ok": True, "total": total})
            return
        if p.path == "/api/admin/settlement/run":
            u = self._require_login_api()
            if not u:
                return
            if not u.get("is_super"):
                self._send_json({"ok": False, "error": "forbidden"}, status=403)
                return
            r = settle_positions()
            self._send_json({"ok": True, "count": r.get("count"), "ts": r.get("ts"), "date": r.get("date")})
            return
        if p.path == "/api/admin/settlement/status":
            s = get_settlement_status()
            self._send_json(s)
            return
        if p.path == "/api/admin/settlement/daily":
            u = self._require_login_api()
            if not u:
                return
            q = parse_qs(p.query or "")
            d = (q.get("date") or [""])[0].strip()
            items = get_user_positions_daily(u.get("id"), d if d else None)
            self._send_json({"items": items})
            return
        if p.path == "/api/admin/settlement/recompute":
            u = self._require_login_api()
            if not u:
                return
            q = parse_qs(p.query or "")
            d = (q.get("date") or [""])[0].strip()
            if not d:
                d = datetime.datetime.now().date().isoformat()
            sums = sum_daily_profit_by_code(u.get("id"), d)
            items = get_user_positions_json(u.get("id")) or []
            to_write = []
            for it in items:
                code = str(it.get("code") or "").strip()
                if not code:
                    continue
                delta = float(sums.get(code) or 0.0)
                total_prev = it.get("total_earnings")
                try:
                    total_prev = float(total_prev) if total_prev is not None else 0.0
                except Exception:
                    total_prev = 0.0
                to_write.append({
                    "code": code,
                    "fund_name": it.get("fund_name"),
                    "amount": it.get("amount"),
                    "earnings_yesterday": delta,
                    "total_earnings": total_prev + delta,
                    "return_rate": it.get("return_rate"),
                    "notes": it.get("notes")
                })
            if to_write:
                upsert_user_positions_json(u.get("id"), to_write)
            self._send_json({"ok": True, "date": d, "updated": len(to_write)})
            return
        if p.path == "/api/funds":
            u = self._require_login_api()
            if not u:
                return
            q = parse_qs(p.query or "")
            raw = (q.get("codes") or [""])[0].strip()
            if not raw:
                self._send_json({"items": []})
                return
            now = datetime.datetime.now()
            after_close = now.hour >= 18
            items = []
            for code in [x.strip() for x in raw.split(",") if x.strip()]:
                obj = get_fund(code) or {}
                est = fetch_fund_estimation(code)
                if est:
                    obj.update(est)
                navc = fetch_latest_nav_change(code) if after_close else None
                today_str = now.date().isoformat()
                use_official = navc and (navc.get("pct") is not None) and (navc.get("date") == today_str)
                if use_official:
                    try:
                        obj["daily_pct"] = float(navc.get("pct"))
                    except Exception:
                        obj["daily_pct"] = None
                    obj["daily_pct_date"] = navc.get("date")
                    obj["pct_source"] = "official"
                    obj["nav_fetched_at"] = now.strftime("%H:%M")
                else:
                    try:
                        obj["daily_pct"] = float((est or {}).get("gszzl") or 0.0)
                    except Exception:
                        obj["daily_pct"] = None
                    obj["pct_source"] = "estimate"
                if obj:
                    items.append(obj)
            self._send_json({"items": items})
            return
        if p.path.startswith("/api/fund/"):
            code = p.path.split("/")[-1]
            obj = get_fund(code) or {}
            est = fetch_fund_estimation(code)
            if est:
                obj.update(est)
            if obj:
                self._send_json(obj)
            else:
                self._send_json({"error": "not_found"}, status=404)
            return
        if p.path == "/api/admin/portfolio":
            u = self._require_login_api()
            if not u:
                return
            self._send_json({"items": get_user_positions_json(u.get("id"))})
            return
        if p.path == "/api/admin/portfolio/codes":
            u = self._require_login_api()
            if not u:
                return
            codes = [it.get("code") for it in get_user_positions_json(u.get("id")) if it.get("code") and not str(it.get("code")).startswith("NOCODE:")]
            self._send_json({"codes": codes})
            return
        if p.path.startswith("/api/admin/fund/local"):
            q = parse_qs(p.query or "")
            code = (q.get("code") or [""])[0].strip()
            if not code:
                self._send_json({"error": "missing_code"}, status=400)
                return
            obj = get_fund(code) or {}
            name = obj.get("name")
            if name:
                self._send_json({"name": name})
            else:
                self._send_json({"error": "not_found"}, status=404)
            return
        if p.path.startswith("/api/admin/fund/profile"):
            q = parse_qs(p.query or "")
            code = (q.get("code") or [""])[0].strip()
            if not code:
                self._send_json({"error": "missing_code"}, status=400)
                return
            prof = fetch_fund_profile(code)
            if prof:
                self._send_json({"profile": prof})
            else:
                self._send_json({"error": "not_found"}, status=404)
            return
        if p.path == "/admin/funds":
            html = """<!doctype html><html><head><meta charset="utf-8"><title>基金资料维护</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:900px;margin:24px auto;padding:0 16px;color:#666}.nav{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #eee;margin-bottom:12px}.nav a{color:#1a73e8;text-decoration:none}.row{display:flex;gap:8px;margin:12px 0}input,textarea{flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;color:#666}button{padding:8px 12px;border:1px solid #1a73e8;background:#1a73e8;color:#fff;border-radius:6px}.muted{color:#888}</style></head><body><h1>基金资料维护</h1><div class="nav"><a href="/">估值</a><a href="/upload-portfolio">个人持仓</a><a href="/admin/funds">基金资料维护</a></div><div class="row"><strong>手动录入</strong></div><div class="row"><input id="code" placeholder="基金代码"><input id="name" placeholder="基金名称"><input id="type" placeholder="类型"><input id="company" placeholder="公司"><input id="managers" placeholder="经理（逗号分隔）"></div><div class="row"><button id="save">保存到本地</button></div><div class="row"><strong>从网上获取并保存</strong></div><div class="row"><input id="fetchCode" placeholder="基金代码"><button id="fetchSave">获取并保存</button></div><div class="row"><span id="status" class="muted"></span></div><script>const statusEl=document.getElementById("status");document.getElementById("save").addEventListener("click",async()=>{const body=new URLSearchParams();const code=document.getElementById("code").value.trim();if(!code){statusEl.textContent="请输入基金代码";return}body.set("code",code);body.set("name",document.getElementById("name").value.trim());body.set("type",document.getElementById("type").value.trim());body.set("company",document.getElementById("company").value.trim());body.set("managers",document.getElementById("managers").value.trim());const r=await fetch("/api/admin/fund/save",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.toString()});const j=await r.json();statusEl.textContent=j.ok?"已保存":"保存失败"});document.getElementById("fetchSave").addEventListener("click",async()=>{const code=document.getElementById("fetchCode").value.trim();if(!code){statusEl.textContent="请输入基金代码";return}const r=await fetch("/api/admin/fund/fetch_save?code="+encodeURIComponent(code),{method:"POST"});const j=await r.json();if(j.ok){statusEl.textContent="已获取并保存："+(j.profile?.name||"")}else{statusEl.textContent="获取失败或未找到"}}</script></body></html>"""
            html += """<div class="row"><strong>一键补充/更新（EastMoney基金代码库）</strong></div><div class="row"><input id="emLimit" placeholder="每批条数（默认500）"><input id="emOffset" placeholder="起始offset（默认0）"><button id="emIngest">批量导入</button></div><div class="row"><div class="progress" style="width:100%;height:8px;background:#eee;border-radius:6px"><div id="emBar" style="height:100%;background:#1a73e8;width:0%;border-radius:6px"></div></div></div><script>document.getElementById("emIngest").addEventListener("click",async()=>{const limRaw=document.getElementById("emLimit").value.trim();const offRaw=document.getElementById("emOffset").value.trim();const chunk=limRaw?parseInt(limRaw,10):500;let offset=offRaw?parseInt(offRaw,10):0;let total=0;let done=0;const bar=document.getElementById("emBar");const statusEl=document.getElementById("status");statusEl.textContent="准备中...";try{const meta=await fetch("/api/admin/eastmoney/fundcodes/meta");if(meta.ok){const j=await meta.json();total=j.total||0}}catch(e){}if(!total){statusEl.textContent="无法获取总量，改为单次导入";const q=new URLSearchParams();if(limRaw) q.set("limit",limRaw);if(offRaw) q.set("offset",offRaw);const r=await fetch("/api/admin/eastmoney/fundcodes/ingest?"+q.toString());const j=await r.json();statusEl.textContent=j.ok?`已导入 ${j.count||0} 条`:"导入失败";bar.style.width="100%";return}statusEl.textContent=`开始导入，共 ${total} 条`;while(offset<total){const q=new URLSearchParams();q.set("limit", String(chunk));q.set("offset", String(offset));const r=await fetch("/api/admin/eastmoney/fundcodes/ingest?"+q.toString());const j=await r.json();if(!j.ok){statusEl.textContent="导入失败";break}done+=j.count||0;offset+=chunk;const pct=Math.min(100, Math.floor(done*100/total));bar.style.width=pct+"%";statusEl.textContent=`已导入 ${done}/${total}`;}if(offset>=total){bar.style.width="100%";statusEl.textContent=`完成，共导入 ${done} 条`;}});</script>"""
            self._send_html(html)
            return
        if p.path == "/admin/users":
            u = self._require_login_page("/admin/users")
            if not u:
                return
            if not u.get("is_super"):
                self._send_html(
                    "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
                    "<title>无权限</title><style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:720px;margin:24px auto;padding:0 16px;color:#666}"
                    "a{color:#1a73e8;text-decoration:none}</style></head><body><h2>无权限</h2><p>此页面仅超级用户可用。</p><p><a href='/'>返回</a></p></body></html>",
                    status=403,
                )
                return
            users = list_users(include_admin=False) or []
            rows = "".join(
                [
                    f"<tr><td>{it.get('id')}</td><td>{it.get('username')}</td><td>{'是' if it.get('is_super') else ''}</td>"
                    f"<td><button class='del' data-u='{it.get('username')}'>删除</button></td></tr>"
                    for it in users
                ]
            )
            html = """<!doctype html><html><head><meta charset="utf-8"><title>管理用户</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:900px;margin:24px auto;padding:0 16px;color:#666}}
h1{{font-size:22px;margin:0 0 12px;color:#666}}
.nav{{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #eee;margin-bottom:12px}}
.nav a{{color:#1a73e8;text-decoration:none}}
.row{{display:flex;gap:8px;margin:12px 0}}
input{{flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;color:#666}}
button{{padding:8px 12px;border:1px solid #1a73e8;background:#1a73e8;color:#fff;border-radius:6px}}
table{{width:100%;border-collapse:collapse;margin-top:12px;color:#666}}
th,td{{border-bottom:1px solid #eee;padding:8px;text-align:left;font-size:14px}}
.muted{{color:#888}}</style></head><body>
<h1>管理用户</h1>
<div class="nav"><a href="/">估值</a><a href="/upload-portfolio">个人持仓</a><a href="/admin/funds">基金资料维护</a><a href="/admin/users">管理用户</a><a href="/logout">登出</a></div>
<div class="row"><input id="nu" placeholder="新用户名" /><input id="np" placeholder="新密码" type="password" /><button id="add">添加</button></div>
<div class="row"><span id="msg" class="muted"></span></div>
<table><thead><tr><th>ID</th><th>用户名</th><th>超级用户</th><th>操作</th></tr></thead><tbody>__ROWS__</tbody></table>
<script>
async function post(url, body){
  const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:body.toString()})
  const j=await r.json()
  return {r,j}
}
document.getElementById("add").addEventListener("click", async ()=>{
  const u=document.getElementById("nu").value.trim()
  const p=document.getElementById("np").value
  const msg=document.getElementById("msg")
  if(!u||!p){msg.textContent="请输入用户名和密码";return}
  const body=new URLSearchParams()
  body.set("username",u); body.set("password",p)
  try{
    const {r,j}=await post("/api/super/users/add", body)
    msg.textContent=(r.status===200&&j.ok)?"已添加":"添加失败："+(j.error||"")
    if(r.status===200&&j.ok) location.reload()
  }catch(e){msg.textContent="添加失败"}
})
document.querySelectorAll("button.del").forEach(btn=>{
  btn.addEventListener("click", async ()=>{
    const u=btn.getAttribute("data-u")
    if(!u||u==="admin") return
    if(!confirm("确定删除用户 "+u+" 吗？")) return
    const body=new URLSearchParams(); body.set("username",u)
    const msg=document.getElementById("msg")
    try{
      const {r,j}=await post("/api/super/users/delete", body)
      msg.textContent=(r.status===200&&j.ok)?"已删除":"删除失败："+(j.error||"")
      if(r.status===200&&j.ok) location.reload()
    }catch(e){msg.textContent="删除失败"}
  })
})
</script></body></html>"""
            html = html.replace("__ROWS__", rows).replace("{{", "{").replace("}}", "}")
            self._send_html(html)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        p = urlparse(self.path)
        # 已移除 /api/admin/holdings/ocr
        # 已移除 /api/admin/portfolio/ocr
        if p.path == "/api/login":
            ck = self._parse_cookies()
            old_tok = ck.get("fw_session")
            if old_tok:
                delete_session(old_tok)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            kv = {}
            try:
                kv = parse_qs(body.decode("utf-8", errors="ignore"))
            except Exception:
                kv = {}
            username = (kv.get("username") or [""])[0].strip()
            password = (kv.get("password") or [""])[0]
            u = authenticate(username, password)
            if not u:
                self._send_json({"ok": False, "error": "invalid_credentials"}, status=401)
                return
            tok = create_session(u.get("id"))
            self._send_json({"ok": True, "username": u.get("username"), "is_super": bool(u.get("is_super"))}, extra_headers={"Set-Cookie": self._set_session_cookie_header(tok)})
            return
        if p.path == "/api/super/users/add":
            u = self._require_login_api()
            if not u:
                return
            if not u.get("is_super"):
                self._send_json({"ok": False, "error": "forbidden"}, status=403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            kv = {}
            try:
                kv = parse_qs(body.decode("utf-8", errors="ignore"))
            except Exception:
                kv = {}
            username = (kv.get("username") or [""])[0].strip()
            password = (kv.get("password") or [""])[0]
            try:
                create_user(username, password, is_super=False)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
                return
            self._send_json({"ok": True})
            return
        if p.path == "/api/super/users/delete":
            u = self._require_login_api()
            if not u:
                return
            if not u.get("is_super"):
                self._send_json({"ok": False, "error": "forbidden"}, status=403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            kv = {}
            try:
                kv = parse_qs(body.decode("utf-8", errors="ignore"))
            except Exception:
                kv = {}
            username = (kv.get("username") or [""])[0].strip()
            deleted = delete_user(username)
            if not deleted:
                self._send_json({"ok": False, "error": "not_found_or_protected"}, status=400)
                return
            self._send_json({"ok": True})
            return
        if p.path == "/api/admin/portfolio/clear":
            u = self._require_login_api()
            if not u:
                return
            clear_user_positions_json(u.get("id"))
            self._send_json({"ok": True})
            return
        if p.path == "/api/admin/portfolio/import_test_data":
            u = self._require_login_api()
            if not u:
                return
            q = parse_qs(p.query or "")
            path = (q.get("path") or [""])[0].strip() or "/Users/wenguanggu/MyProjects/Python/FundValuationWatcher/fundwatcher/test_data/funds.json"
            try:
                with open(path, "rb") as f:
                    raw = f.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
            except Exception:
                self._send_json({"error": "read_failed"}, status=400)
                return
            items = []
            if not isinstance(data, list):
                self._send_json({"error": "invalid_format", "expected": "array"}, status=400)
                return
            arr = data
            for it in arr:
                name = (it.get("fund_name") or it.get("name") or "").strip()
                if not name:
                    continue
                amount = it.get("amount")
                yp = it.get("earnings_yesterday")
                hr = it.get("return_rate")
                code = find_fund_code_by_name(name)
                if not code:
                    continue
                items.append({"code": code, "fund_name": name, "amount": amount, "earnings_yesterday": yp, "total_earnings": it.get("total_earnings"), "return_rate": hr, "notes": it.get("notes")})
            if items:
                upsert_user_positions_json(u.get("id"), items)
            self._send_json({"ok": True, "count": len(items)})
            return
        if p.path == "/api/admin/portfolio/json":
            u = self._require_login_api()
            if not u:
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            items = []
            try:
                j = json.loads(body.decode("utf-8", errors="ignore"))
                if not isinstance(j, list):
                    self._send_json({"error": "invalid_format", "expected": "array"}, status=400)
                    return
                items = j
            except Exception:
                items = []
            filled = []
            for it in items:
                code = str(it.get("code") or "").strip()
                fund_name = (it.get("fund_name") or "").strip()
                if not code:
                    c2 = find_fund_code_by_name(fund_name)
                    if c2:
                        code = c2
                if not code and fund_name:
                    code = "NOCODE:" + fund_name
                if not code:
                    continue
                filled.append({"code": code, "fund_name": fund_name, "amount": it.get("amount"), "earnings_yesterday": it.get("earnings_yesterday"), "total_earnings": it.get("total_earnings"), "return_rate": it.get("return_rate"), "notes": it.get("notes")})
            commit = ((parse_qs(p.query or "").get("commit") or ["1"])[0].strip().lower() in ("1","true","yes"))
            if filled and commit:
                upsert_user_positions_json(u.get("id"), filled)
            self._send_json({"ok": True, "count": len(filled), "items": filled, "committed": bool(filled and commit)})
            return
        if p.path == "/api/admin/portfolio/add":
            u = self._require_login_api()
            if not u:
                return
            q = parse_qs(p.query or "")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            kv = {}
            try:
                kv = parse_qs(body.decode("utf-8", errors="ignore"))
            except Exception:
                kv = {}
            code = (kv.get("code") or [""])[0].strip()
            fund_name = (kv.get("fund_name") or [""])[0].strip()
            amount = (kv.get("amount") or [""])[0].strip()
            ey = (kv.get("earnings_yesterday") or [""])[0].strip()
            te = (kv.get("total_earnings") or [""])[0].strip()
            rate = (kv.get("return_rate") or [""])[0].strip()
            notes = (kv.get("notes") or [""])[0].strip()
            if not code:
                self._send_json({"error": "missing_code"}, status=400)
                return
            amt = float(amount) if amount else None
            eyy = float(ey) if ey else None
            tee = float(te) if te else None
            rr = float(rate) if rate else None
            upsert_user_positions_json(u.get("id"), [{"code": code, "fund_name": fund_name or None, "amount": amt, "earnings_yesterday": eyy, "total_earnings": tee, "return_rate": rr, "notes": (notes or None)}])
            self._send_json({"ok": True})
            return
        if p.path == "/api/admin/portfolio/update":
            u = self._require_login_api()
            if not u:
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            kv = {}
            try:
                kv = parse_qs(body.decode("utf-8", errors="ignore"))
            except Exception:
                kv = {}
            code = (kv.get("code") or [""])[0].strip()
            if not code:
                self._send_json({"error": "missing_code"}, status=400)
                return
            new_code = (kv.get("new_code") or [""])[0].strip()
            fund_name = (kv.get("fund_name") or [""])[0].strip()
            amt = (kv.get("amount") or [""])[0].strip()
            ey = (kv.get("earnings_yesterday") or [""])[0].strip()
            te = (kv.get("total_earnings") or [""])[0].strip()
            rr = (kv.get("return_rate") or [""])[0].strip()
            nt = (kv.get("notes") or [""])[0].strip()

            existing_items = get_user_positions_json(u.get("id")) or []
            existing_map = {str(it.get("code") or "").strip(): it for it in existing_items}
            cur = existing_map.get(code)
            if not cur:
                self._send_json({"ok": False, "error": "持仓不存在"}, status=404)
                return

            target_code = new_code or code
            if target_code != code and existing_map.get(target_code):
                self._send_json({"ok": False, "error": "该基金代码已存在持仓"}, status=400)
                return

            target_fund_name = None
            if target_code != code:
                prof = get_fund(target_code)
                if not prof:
                    self._send_json({"ok": False, "error": "基金代码不存在"}, status=400)
                    return
                target_fund_name = prof.get("name")
            else:
                target_fund_name = fund_name or cur.get("fund_name")
                if not target_fund_name:
                    prof = get_fund(target_code)
                    if prof:
                        target_fund_name = prof.get("name")

            def _to_float_or_keep(raw, old):
                raw = str(raw or "").strip()
                if raw == "":
                    return old
                return float(raw)

            payload = {
                "code": target_code,
                "fund_name": target_fund_name or None,
                "amount": _to_float_or_keep(amt, cur.get("amount")),
                "earnings_yesterday": _to_float_or_keep(ey, cur.get("earnings_yesterday")),
                "total_earnings": _to_float_or_keep(te, cur.get("total_earnings")),
                "return_rate": _to_float_or_keep(rr, cur.get("return_rate")),
                "notes": (nt if nt != "" else cur.get("notes")) or None,
            }

            if target_code != code:
                delete_user_position_json(u.get("id"), code)
            upsert_user_positions_json(u.get("id"), [payload])
            self._send_json({"ok": True})
            return
        if p.path == "/api/admin/portfolio/delete":
            u = self._require_login_api()
            if not u:
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            kv = {}
            try:
                kv = parse_qs(body.decode("utf-8", errors="ignore"))
            except Exception:
                kv = {}
            code = (kv.get("code") or [""])[0].strip()
            if not code:
                self._send_json({"error": "missing_code"}, status=400)
                return
            delete_user_position_json(u.get("id"), code)
            self._send_json({"ok": True})
            return
        if p.path == "/api/admin/portfolio/delete_batch":
            u = self._require_login_api()
            if not u:
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            codes = []
            try:
                j = json.loads(body.decode("utf-8", errors="ignore"))
                if isinstance(j, dict):
                    codes = j.get("codes") or []
                elif isinstance(j, list):
                    codes = j
            except Exception:
                codes = []
            codes = [str(x or "").strip() for x in (codes or []) if str(x or "").strip()]
            if not codes:
                self._send_json({"ok": False, "error": "请选择要删除的持仓"}, status=400)
                return
            deleted = 0
            for cd in codes:
                deleted += int(delete_user_position_json(u.get("id"), cd) or 0)
            self._send_json({"ok": True, "deleted": deleted})
            return
        if p.path == "/api/admin/portfolio/complete_codes":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            items = []
            try:
                j = json.loads(body.decode("utf-8", errors="ignore"))
                if not isinstance(j, list):
                    self._send_json({"error": "invalid_format", "expected": "array"}, status=400)
                    return
                items = j
            except Exception:
                items = []
            completed = 0
            not_found = []
            out = []
            for it in items:
                code = str(it.get("code") or "").strip()
                fund_name = (it.get("fund_name") or it.get("name") or "").strip()
                if not code:
                    c2 = find_fund_code_by_name(fund_name)
                    if c2:
                        code = c2
                        completed += 1
                    else:
                        if fund_name:
                            not_found.append(fund_name)
                obj = {"code": code or None, "fund_name": fund_name or None, "amount": it.get("amount"), "earnings_yesterday": it.get("earnings_yesterday"), "total_earnings": it.get("total_earnings"), "return_rate": it.get("return_rate"), "notes": it.get("notes")}
                out.append(obj)
            self._send_json({"items": out, "completed": completed, "not_found": not_found})
            return
        if p.path == "/api/admin/fund/save":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            kv = {}
            try:
                kv = parse_qs(body.decode("utf-8", errors="ignore"))
            except Exception:
                kv = {}
            code = (kv.get("code") or [""])[0].strip()
            if not code:
                self._send_json({"ok": False, "error": "missing_code"}, status=400)
                return
            name = (kv.get("name") or [""])[0].strip() or None
            type_ = (kv.get("type") or [""])[0].strip() or None
            company = (kv.get("company") or [""])[0].strip() or None
            managers_raw = (kv.get("managers") or [""])[0].strip()
            managers = [x.strip() for x in managers_raw.split(",") if x.strip()] if managers_raw else None
            upsert_fund_profile(code, name, type_, company, managers)
            self._send_json({"ok": True})
            return
        if p.path.startswith("/api/admin/fund/fetch_save"):
            q = parse_qs(p.query or "")
            code = (q.get("code") or [""])[0].strip()
            if not code:
                self._send_json({"ok": False, "error": "missing_code"}, status=400)
                return
            prof = fetch_fund_profile(code)
            if not prof:
                self._send_json({"ok": False, "error": "not_found"})
                return
            upsert_fund_profile(code, prof.get("name"), prof.get("type"), prof.get("company"), prof.get("managers"))
            self._send_json({"ok": True, "profile": prof})
            return
        self.send_response(404)
        self.end_headers()

def get_config():
    path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            j = json.load(f)
            sec = int(j.get("refresh_interval_seconds") or 55)
            if sec <= 0:
                sec = 55
            return {"refresh_interval_seconds": sec}
    except Exception:
        return {"refresh_interval_seconds": 55}

_last_settlement_info = {"date": None, "ts": None, "slot": None}
_SLOTS = [(22,30,"22:30"),(23,0,"23:00"),(23,30,"23:30"),(23,50,"23:50")]
def _current_slot_label(now):
    hh = now.hour
    mm = now.minute
    for h, m, lab in _SLOTS:
        if h == hh and m == mm:
            return lab
    # fallback: choose the closest slot passed within 5 minutes
    for h, m, lab in _SLOTS:
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if 0 <= (now - t).total_seconds() <= 300:
            return lab
    return f"{hh:02d}:{mm:02d}"
def settle_positions(time_slot="close", do_rollup=False):
    now = datetime.datetime.now()
    slot = _current_slot_label(now)
    date_str = now.date().isoformat()
    cnt = 0
    for uid in list_user_ids(include_admin=True):
        items = get_user_positions_json(uid) or []
        daily_batch = []
        to_update = []
        for it in items:
            code = str(it.get("code") or "").strip()
            if not code or code.startswith("NOCODE:"):
                continue
            amt = float(it.get("amount") or 0) or 0.0
            est = fetch_fund_estimation(code)
            pct = None
            navc = fetch_latest_nav_change(code)
            if navc and navc.get("pct") is not None:
                try:
                    pct = float(navc.get("pct"))
                except Exception:
                    pct = None
            if pct is None:
                if not est:
                    continue
                pct = float(est.get("gszzl") or 0) if est.get("gszzl") is not None else 0.0
            prof = amt * pct / 100.0 if amt and pct else 0.0
            obj = get_fund(code) or {}
            name = obj.get("name")
            daily_batch.append({
                "code": code,
                "fund_name": name or it.get("fund_name"),
                "amount": amt,
                "return_rate": pct,
                "profit": prof
            })
            to_update.append({
                "code": code,
                "fund_name": it.get("fund_name"),
                "amount": it.get("amount"),
                "earnings_yesterday": prof,
                "total_earnings": it.get("total_earnings"),
                "return_rate": pct,
                "notes": it.get("notes")
            })
            cnt += 1
        if daily_batch:
            upsert_user_positions_daily(uid, daily_batch, date_str, time_slot)
        if to_update:
            upsert_user_positions_json(uid, to_update)
        if do_rollup and daily_batch:
            prof_map = {str(x.get("code") or "").strip(): x for x in daily_batch}
            items_cur = get_user_positions_json(uid) or []
            to_write = []
            for it in items_cur:
                code = str(it.get("code") or "").strip()
                if not code:
                    continue
                rec = prof_map.get(code) or {}
                delta = float(rec.get("profit") or 0.0)
                total_prev = it.get("total_earnings")
                try:
                    total_prev = float(total_prev) if total_prev is not None else 0.0
                except Exception:
                    total_prev = 0.0
                to_write.append({
                    "code": code,
                    "fund_name": it.get("fund_name"),
                    "amount": it.get("amount"),
                    "earnings_yesterday": delta,
                    "total_earnings": total_prev + delta,
                    "return_rate": rec.get("return_rate"),
                    "notes": it.get("notes")
                })
            if to_write:
                upsert_user_positions_json(uid, to_write)
    _last_settlement_info["date"] = date_str
    _last_settlement_info["ts"] = int(now.timestamp())
    _last_settlement_info["slot"] = slot
    return {"count": cnt, "date": date_str, "ts": _last_settlement_info["ts"], "slot": slot}

def get_settlement_status():
    d = _last_settlement_info.get("date")
    ts = _last_settlement_info.get("ts")
    return {"ok": True, "last_date": d, "last_ts": ts}

def _seconds_until(target_h, target_m):
    now = datetime.datetime.now()
    target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
    if target <= now:
        target = target + datetime.timedelta(days=1)
    return max(1, int((target - now).total_seconds()))

def start_settlement_scheduler():
    times = []
    h = 18
    m = 0
    while True:
        if h > 23 or (h == 23 and m > 30):
            break
        times.append((h, m))
        m += 30
        if m >= 60:
            h += 1
            m = 0
    times.append((23, 50))
    def loop():
        while True:
            now = datetime.datetime.now()
            secs = None
            for h,m in times:
                t = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if t > now:
                    secs = int((t - now).total_seconds())
                    break
            if secs is None:
                t = now.replace(hour=times[0][0], minute=times[0][1], second=0, microsecond=0) + datetime.timedelta(days=1)
                secs = int((t - now).total_seconds())
            time.sleep(max(1, min(secs, 3600)))
            try:
                now2 = datetime.datetime.now()
                do_rollup = (now2.hour == 23 and now2.minute == 50)
                settle_positions(time_slot="close", do_rollup=do_rollup)
            except Exception:
                pass
    th = threading.Thread(target=loop, daemon=True)
    th.start()

def run(port=8000):
    init_db()
    init_users_db()
    start_settlement_scheduler()
    httpd = ThreadingHTTPServer(("", port), Handler)
    httpd.serve_forever()
