/ ======================================================
// 🏎️ F1 OS v2
// CORE CONFIG
// ======================================================

const fm = FileManager.local();

const ROOT_DIR = fm.joinPath(
  fm.documentsDirectory(),
  "f1_os"
);

if (!fm.fileExists(ROOT_DIR)) {
  fm.createDirectory(ROOT_DIR);
}

const CACHE_TTL = 900;
const NEWS_CACHE_TTL = 600;

// ======================================================
// FILES
// ======================================================

const FILES = {

  data:
    fm.joinPath(ROOT_DIR, "f1_data.json"),

  news:
    fm.joinPath(ROOT_DIR, "news_data.json"),

  wallpaper:
    fm.joinPath(ROOT_DIR, "wallpaper.jpg"),

  circuits:
    fm.joinPath(ROOT_DIR, "circuits.json")

};

// ======================================================
// API URLS
// ======================================================

const URLS = {

  wallpaper:
    "https://raw.githubusercontent.com/zeroOSeven-AI/Scriptable-F1/main/Formula1.JPG",

  circuits:
    "https://raw.githubusercontent.com/zeroOSeven-AI/Scriptable-F1/main/F1 Circuits/circuits.json",

  nextRace:
    "https://api.jolpi.ca/ergast/f1/current/next.json",

  standings:
    "https://api.jolpi.ca/ergast/f1/current/driverStandings.json",

  constructors:
    "https://api.jolpi.ca/ergast/f1/current/constructorStandings.json"

};

// ======================================================
// NEWS ENGINE
// ======================================================

const NEWS_BASE =
  "https://raw.githubusercontent.com/zeroOSeven-AI/News-Sport-/main/";

const SOURCES = {

  sportske: "sportske.json",

  bild: "bild.json",

  espn: "espn.json",

  marca: "marca.json"

};

// ======================================================
// TEAM COLORS
// ======================================================

const TEAM_COLORS = {

  "Red Bull":"#3671C6",
  "red_bull":"#3671C6",

  "McLaren":"#FF8000",
  "mclaren":"#FF8000",

  "Ferrari":"#E80020",
  "ferrari":"#E80020",

  "Mercedes":"#27F4D2",
  "mercedes":"#27F4D2",

  "Aston Martin":"#229971",
  "aston_martin":"#229971",

  "Alpine":"#0093CC",
  "alpine":"#0093CC",

  "Haas F1 Team":"#B6BABD",
  "haas":"#B6BABD",

  "RB F1 Team":"#6692FF",
  "rb":"#6692FF",

  "Williams":"#64C4FF",
  "williams":"#64C4FF",

  "Sauber":"#52E252",
  "sauber":"#52E252"
};

// ======================================================
// DRIVER FLAGS
// ======================================================

const DRIVER_FLAGS = {

  VER:"🇳🇱",
  NOR:"🇬🇧",
  LEC:"🇲🇨",
  PIA:"🇦🇺",
  SAI:"🇪🇸",

  HAM:"🇬🇧",
  RUS:"🇬🇧",
  PER:"🇲🇽",

  ALO:"🇪🇸",
  STR:"🇨🇦",

  TSU:"🇯🇵",

  HUL:"🇩🇪",

  GAS:"🇫🇷",
  OCO:"🇫🇷",

  ALB:"🇹🇭",

  BEA:"🇬🇧",

  MAG:"🇩🇰",

  ZHO:"🇨🇳",

  BOT:"🇫🇮",

  COL:"🇦🇷"
};

// ======================================================
// TEAM NAMES
// ======================================================

const TEAM_NAMES = {

  red_bull:"Oracle Red Bull",

  mclaren:"McLaren F1 Team",

  ferrari:"Scuderia Ferrari",

  mercedes:"Mercedes AMG",

  aston_martin:"Aston Martin F1",

  alpine:"Alpine F1 Team",

  haas:"Haas F1 Team",

  rb:"Visa Cash App RB",

  williams:"Williams Racing",

  sauber:"Stake Sauber"
};

// ======================================================
// THEME
// ======================================================

const CONST_THEME = {

  accent:
    new Color("#e10600"),

  glass:
    new Color("#000000",0.60),

  border:
    new Color("#ffffff",0.10)

};

// ======================================================
// CACHE HELPERS
// ======================================================

function cacheValid(path, ttl = CACHE_TTL) {

  if (!fm.fileExists(path))
    return false;

  const age =
    (Date.now() -
    fm.creationDate(path).getTime()) / 1000;

  return age < ttl;
}

function saveJSON(path,data){

  fm.writeString(
    path,
    JSON.stringify(data)
  );
}

function loadJSON(path){

  try{
    return JSON.parse(
      fm.readString(path)
    );
  }catch(e){
    return null;
  }
}

// ======================================================
// FETCH HELPERS
// ======================================================

async function fetchJSON(url){

  const r = new Request(url);

  r.timeoutInterval = 15;

  return await r.loadJSON();
}

async function fetchImage(url){

  const r = new Request(url);

  r.timeoutInterval = 20;

  return await r.loadImage();
}

// ======================================================
// WALLPAPER
// ======================================================

async function loadWallpaper(){

  try{

    if(fm.fileExists(FILES.wallpaper)){
      return fm.readImage(FILES.wallpaper);
    }

    const img =
      await fetchImage(
        URLS.wallpaper
      );

    fm.writeImage(
      FILES.wallpaper,
      img
    );

    return img;

  }catch(e){

    console.log(e);

    return null;
  }
}

// ======================================================
// F1 DATA
// ======================================================

async function loadF1Data(){

  try{

    if(cacheValid(FILES.data)){
      return loadJSON(FILES.data);
    }

    const [
      nextRace,
      standings,
      constructors
    ] = await Promise.all([

      fetchJSON(URLS.nextRace),

      fetchJSON(URLS.standings),

      fetchJSON(URLS.constructors)

    ]);

    let circuits =
      loadJSON(FILES.circuits);

    if(!circuits){

      circuits =
        await fetchJSON(
          URLS.circuits
        );

      saveJSON(
        FILES.circuits,
        circuits
      );
    }

    const data = {

      race:
        nextRace.MRData
        .RaceTable
        .Races[0],

      standings:
        standings.MRData
        .StandingsTable
        .StandingsLists[0]
        .DriverStandings,

      constructors:
        constructors.MRData
        .StandingsTable
        .StandingsLists[0]
        .ConstructorStandings,

      circuits,

      updated:
        new Date()
        .toISOString()
    };

    saveJSON(
      FILES.data,
      data
    );

    return data;

  }catch(e){

    console.log(e);

    return loadJSON(FILES.data);
  }
}

// ======================================================
// NEWS DATA
// ======================================================

async function loadNewsData(){

  try{

    if(
      cacheValid(
        FILES.news,
        NEWS_CACHE_TTL
      )
    ){
      return loadJSON(FILES.news);
    }

    const requests =
      Object.values(SOURCES)
      .map(file =>
        fetchJSON(
          NEWS_BASE + file
        )
      );

    const results =
      await Promise.allSettled(
        requests
      );

    let allNews = [];

    results.forEach(result=>{

      if(
        result.status === "fulfilled"
        &&
        Array.isArray(result.value)
      ){

        allNews.push(
          ...result.value
        );
      }

    });

    allNews.sort((a,b)=>{

      const d1 =
        new Date(
          b.pubDate || 0
        );

      const d2 =
        new Date(
          a.pubDate || 0
        );

      return d1-d2;
    });

    saveJSON(
      FILES.news,
      allNews
    );

    return allNews;

  }catch(e){

    console.log(e);

    return loadJSON(FILES.news) || [];
  }
}

// ======================================================
// CSS MODULES
// ======================================================

const CORE_CSS = `

*{
  margin:0;
  padding:0;
  box-sizing:border-box;
}

html{
  height:100%;
}

body{

  height:100%;

  background:#07090e;

  color:#e2e8f0;

  font-family:
  -apple-system,
  BlinkMacSystemFont,
  sans-serif;

  overflow:hidden;
}

a{
  text-decoration:none;
}

`;


// ======================================================
// HEADER
// ======================================================

const HEADER_CSS = `

.header{

  height:60px;

  display:flex;

  align-items:center;

  justify-content:center;

  font-size:15px;

  font-weight:700;

  letter-spacing:1px;

  color:#a0aec0;

  background:
  rgba(0,0,0,.25);

  backdrop-filter:
  blur(20px);

  border-bottom:
  1px solid
  rgba(255,255,255,.04);
}

`;


// ======================================================
// PAGE SYSTEM
// ======================================================

const PAGE_CSS = `

.slider{

  display:flex;

  width:400vw;

  height:calc(100vh - 125px);

  transition:
  transform .28s
  cubic-bezier(
    0.16,
    1,
    0.3,
    1
  );
}

.page{

  width:100vw;

  height:100%;

  overflow-y:auto;

  padding:
  16px
  16px
  40px
  16px;
}

.page::-webkit-scrollbar{
  display:none;
}

`;


// ======================================================
// CARD SYSTEM
// ======================================================

const CARD_CSS = `

.card{

  background:
  rgba(255,255,255,.02);

  border:
  1px solid
  rgba(255,255,255,.05);

  border-radius:18px;

  padding:16px;

  margin-bottom:12px;
}

.badge{

  color:#a0aec0;

  font-size:10px;

  font-weight:700;

  text-transform:uppercase;

  letter-spacing:.5px;

  opacity:.65;

  margin-bottom:8px;
}

.title{

  font-size:21px;

  font-weight:700;

  color:white;
}

.sub{

  margin-top:4px;

  font-size:12px;

  opacity:.5;
}

`;


// ======================================================
// STANDINGS
// ======================================================

const STANDINGS_CSS = `

.row{

  display:flex;

  justify-content:space-between;

  align-items:center;

  padding:10px 0;

  border-bottom:
  1px solid
  rgba(255,255,255,.03);
}

.row:last-child{
  border-bottom:none;
}

.team-core{

  display:flex;

  align-items:center;

  gap:10px;
}

.color-indicator{

  width:3px;

  height:20px;

  border-radius:2px;
}

.main-name{

  font-size:14px;

  font-weight:600;

  color:white;
}

.sub-team-app{

  font-size:11px;

  color:#a0aec0;

  margin-top:2px;

  font-style:italic;
}

.rank{

  display:inline-block;

  width:18px;

  color:#718096;

  font-weight:700;
}

.score-points{

  color:white;

  font-size:14px;

  font-weight:700;
}

.score-points small{

  font-size:9px;

  color:#a0aec0;
}

`;


// ======================================================
// SESSION TABLE
// ======================================================

const SESSION_CSS = `

.session-row{

  display:flex;

  justify-content:space-between;

  align-items:center;

  padding:10px 0;

  border-bottom:
  1px solid
  rgba(255,255,255,.03);
}

.session-row:last-child{
  border-bottom:none;
}

.session-name{

  flex:1;

  font-size:14px;

  font-weight:600;

  color:white;
}

.session-date{

  font-size:11px;

  opacity:.4;

  margin-right:10px;
}

.session-time{

  font-size:14px;

  font-weight:700;

  color:#44dfb6;
}

`;


// ======================================================
// CIRCUIT MAP
// ======================================================

const MAP_CSS = `

.map-box{

  display:flex;

  justify-content:center;

  align-items:center;

  padding:12px;

  margin-top:12px;

  border-radius:12px;

  background:
  rgba(0,0,0,.20);
}

.map{

  width:100%;

  max-height:220px;

  object-fit:contain;

  filter:
  invert(1)
  brightness(1.8)
  contrast(1.2);
}

`;


// ======================================================
// NEWS SYSTEM
// ======================================================

const NEWS_CSS = `

.news-nav{

  display:flex;

  justify-content:space-between;

  align-items:center;

  margin-bottom:12px;

  font-size:10px;

  color:#888;
}

.news-nav span{

  cursor:pointer;
}

.news-container{

  display:grid;

  grid-template-columns:
  1fr
  1fr;

  gap:10px;
}

.list-view{

  display:block;
}

.news-card{

  background:#121212;

  border-radius:12px;

  overflow:hidden;

  cursor:pointer;
}

.news-thumb{

  width:100%;

  height:120px;

  object-fit:cover;
}

.news-content{

  padding:10px;
}

.news-meta{

  font-size:9px;

  font-weight:800;

  text-transform:uppercase;

  margin-bottom:4px;
}

.news-title{

  font-size:13px;

  font-weight:600;

  line-height:1.3;

  color:white;
}

.list-view .news-card{

  display:flex;

  margin-bottom:10px;
}

.list-view .news-thumb{

  width:120px;

  height:100px;
}

.list-view .news-content{

  flex:1;
}

`;


// ======================================================
// TAB BAR
// ======================================================

const TAB_CSS = `

.tabs{

  position:fixed;

  bottom:0;

  left:0;

  right:0;

  height:65px;

  display:flex;

  background:
  rgba(5,7,12,.95);

  backdrop-filter:
  blur(20px);

  border-top:
  1px solid
  rgba(255,255,255,.05);
}

.tab{

  flex:1;

  display:flex;

  align-items:center;

  justify-content:center;

  font-size:10px;

  font-weight:700;

  color:#a0aec0;

  opacity:.45;

  cursor:pointer;
}

.tab.active{

  opacity:1;

  color:#e10600;

  border-top:
  2px solid
  #e10600;
}

`;


// ======================================================
// FINAL CSS
// ======================================================

const CSS = `

${CORE_CSS}

${HEADER_CSS}

${PAGE_CSS}

${CARD_CSS}

${STANDINGS_CSS}

${SESSION_CSS}

${MAP_CSS}

${NEWS_CSS}

${TAB_CSS}

`;


// ======================================================
// UI ENGINE
// ======================================================

const UI_SCRIPT = `

let currentPage = 0;

function go(index){

  currentPage = index;

  document
    .getElementById("slider")
    .style.transform =
      "translateX(-" +
      (index * 100) +
      "vw)";

  document
    .querySelectorAll(".tab")
    .forEach((tab,i)=>{

      tab.classList.toggle(
        "active",
        i === index
      );

    });
}

// ======================================================
// SWIPE ENGINE
// ======================================================

let startX = 0;

document.addEventListener(
  "touchstart",
  e=>{

    startX =
      e.touches[0].clientX;

  },
  {passive:true}
);

document.addEventListener(
  "touchend",
  e=>{

    const diff =
      startX -
      e.changedTouches[0].clientX;

    if(diff > 60 && currentPage < 3){

      go(currentPage + 1);
    }

    if(diff < -60 && currentPage > 0){

      go(currentPage - 1);
    }

  },
  {passive:true}
);

// ======================================================
// NEWS VIEW
// ======================================================

function toggleNews(mode){

  const el =
    document.getElementById(
      "news-container"
    );

  if(mode === "list"){

    el.className =
      "list-view";

  }else{

    el.className =
      "news-container";
  }
}

// ======================================================
// NEWS FILTER
// ======================================================

function filterNews(source){

  const cards =
    document.querySelectorAll(
      ".news-card"
    );

  cards.forEach(card=>{

    if(
      source === "all"
    ){

      card.style.display =
        "";

      return;
    }

    const current =
      card.dataset.source;

    card.style.display =
      current === source
      ? ""
      : "none";

  });
}

`;

// ======================================================
// PAGE COMPONENTS
// ======================================================


// ======================================================
// RACE PAGE
// ======================================================

function generateRacePage(data){

  const race = data.race;

  const circuitKey =
    race?.Circuit
    ?.circuitId
    ?.toLowerCase();

  const mapUrl =
    data?.circuits
    ?.direct_circuit_maps
    ?.[circuitKey] || "";

  const raceDate =
    new Date(
      race.date +
      "T" +
      (race.time || "12:00:00Z")
    );

  const days =
    Math.ceil(
      (raceDate - new Date())
      /
      (1000 * 60 * 60 * 24)
    );

  const countdownText =
    days > 0
    ? `${days} DAYS TO GO`
    : "RACE WEEKEND LIVE";

  const qualyTime =
    race.Qualifying?.time
    ? race.Qualifying.time.substring(0,5)
    : "--:--";

  const qualyDate =
    race.Qualifying?.date
    || race.date;

  const raceTime =
    race.time
    ? race.time.substring(0,5)
    : "--:--";

  return `

  <div class="page">

    <div class="card">

      <div class="badge">
        WEEKEND STATUS
      </div>

      <div
        class="title"
        style="color:#e10600;font-size:18px;"
      >
        ${countdownText}
      </div>

    </div>

    <div class="card">

      <div class="badge">
        EVENT INFO
      </div>

      <div class="title">
        ${race.raceName}
      </div>

      <div class="sub">
        ${race.Circuit.Location.locality},
        ${race.Circuit.Location.country}
      </div>

    </div>

    <div class="card">

      <div class="badge">
        SESSION TIMETABLE
      </div>

      <div class="session-row">

        <div class="session-name">
          Qualifying
        </div>

        <div class="session-date">
          ${qualyDate}
        </div>

        <div class="session-time">
          ${qualyTime}
        </div>

      </div>

      <div class="session-row">

        <div
          class="session-name"
          style="color:#e10600;"
        >
          Grand Prix
        </div>

        <div class="session-date">
          ${race.date}
        </div>

        <div
          class="session-time"
          style="color:#e10600;"
        >
          ${raceTime}
        </div>

      </div>

    </div>

    <div class="card">

      <div class="badge">
        CIRCUIT LAYOUT
      </div>

      <div
        class="sub"
        style="
          color:white;
          opacity:1;
          font-weight:600;
        "
      >
        ${race.Circuit.circuitName}
      </div>

      <div class="map-box">

        ${
          mapUrl
          ?
          `<img
             class="map"
             src="${mapUrl}"
           >`
          :
          `<div class="sub">
             MAP NOT AVAILABLE
           </div>`
        }

      </div>

    </div>

  </div>

  `;
}


// ======================================================
// DRIVERS PAGE
// ======================================================

function generateDriversPage(data){

  let html = "";

  data.standings.forEach((driver,index)=>{

    const constructorId =
      driver.Constructors[0]
      ?.constructorId;

    const teamColor =
      TEAM_COLORS[constructorId]
      || "#ffffff";

    const driverCode =
      driver.Driver.code
      ||
      driver.Driver.familyName
      .substring(0,3)
      .toUpperCase();

    const flag =
      DRIVER_FLAGS[driverCode]
      || "🏁";

    html += `

    <div class="row">

      <div class="team-core">

        <span
          class="color-indicator"
          style="
            background:${teamColor};
          "
        ></span>

        <div>

          <div class="main-name">

            <span class="rank">
              ${index + 1}
            </span>

            ${flag}

            ${driver.Driver.givenName}

            ${driver.Driver.familyName}

          </div>

          <div class="sub-team-app">

            ${
              TEAM_NAMES[
                constructorId
              ]
              ||
              driver.Constructors[0]
              ?.name
            }

          </div>

        </div>

      </div>

      <span class="score-points">

        ${driver.points}

        <small>PTS</small>

      </span>

    </div>

    `;

  });

  return `

  <div class="page">

    <div class="card">

      <div class="badge">
        DRIVER STANDINGS
      </div>

      ${html}

    </div>

  </div>

  `;
}


// ======================================================
// TEAMS PAGE
// ======================================================

function generateTeamsPage(data){

  let html = "";

  data.constructors.forEach((team,index)=>{

    const constructorId =
      team.Constructor
      .constructorId;

    const color =
      TEAM_COLORS[
        constructorId
      ] || "#ffffff";

    html += `

    <div class="row">

      <div class="team-core">

        <span
          class="color-indicator"
          style="
            background:${color};
          "
        ></span>

        <div>

          <div class="main-name">

            <span class="rank">
              ${index + 1}
            </span>

            ${
              TEAM_NAMES[
                constructorId
              ]
              ||
              team.Constructor.name
            }

          </div>

        </div>

      </div>

      <span class="score-points">

        ${team.points}

        <small>PTS</small>

      </span>

    </div>

    `;

  });

  return `

  <div class="page">

    <div class="card">

      <div class="badge">
        CONSTRUCTOR STANDINGS
      </div>

      ${html}

    </div>

  </div>

  `;
}


// ======================================================
// NEWS PAGE
// ======================================================

function generateNewsPage(newsItems){

  const cards =
    newsItems.map(item => {

      const source =
        (
          item.source_title2 ||
          "unknown"
        )
        .toLowerCase();

      return `

      <div
        class="news-card"
        data-source="${source}"
        onclick="
          window.location.href=
          '${item.link}'
        "
      >

        <img
          src="${item.image_url}"
          class="news-thumb"
        >

        <div class="news-content">

          <div
            class="news-meta"
            style="
              color:
              ${item.source_color || "#888"};
            "
          >

            ${item.source_title1 || ""}

            |

            ${item.source_title2 || ""}

            ${item.flag || ""}

          </div>

          <div class="news-title">

            ${item.title}

          </div>

        </div>

      </div>

      `;

    }).join("");

  return `

  <div class="page">

    <div class="news-nav">

      <div>

        <span
          onclick="
            filterNews('all')
          "
        >
          ALL
        </span>

      </div>

      <div>

        <span
          onclick="
            toggleNews('list')
          "
        >
          LIST
        </span>

        •

        <span
          onclick="
            toggleNews('grid')
          "
        >
          GRID
        </span>

      </div>

    </div>

    <div
      id="news-container"
      class="news-container"
    >

      ${cards}

    </div>

  </div>

  `;
}

// ======================================================
// HTML GENERATOR
// ======================================================

function generateHTML(data, news){

  return `

  <!DOCTYPE html>
  <html>

  <head>

    <meta charset="utf-8">

    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0, maximum-scale=1.0"
    >

    <style>
      ${CSS}
    </style>

  </head>

  <body>

    <div class="header">
      F1 INFO CENTER
    </div>

    <div
      id="slider"
      class="slider"
    >

      ${generateRacePage(data)}

      ${generateDriversPage(data)}

      ${generateTeamsPage(data)}

      ${generateNewsPage(news)}

    </div>

    <div class="tabs">

      <div
        class="tab active"
        onclick="go(0)"
      >
        RACE
      </div>

      <div
        class="tab"
        onclick="go(1)"
      >
        DRIVERS
      </div>

      <div
        class="tab"
        onclick="go(2)"
      >
        TEAMS
      </div>

      <div
        class="tab"
        onclick="go(3)"
      >
        NEWS
      </div>

    </div>

    <script>
      ${UI_SCRIPT}
    </script>

  </body>

  </html>

  `;
}

// ======================================================
// PREMIUM HOME SCREEN WIDGET (DYNAMIC SIZES & FIXED LAYOUT)
// ======================================================
async function createWidget(data, wallpaper) {
  const w = new ListWidget();
  w.url = URLScheme.forRunningScript(); 
  
  const isMedium = config.widgetFamily === "medium";
  
  // Siguran i fiksni padding za savršen odmak teksta od ruba
  w.setPadding(14, 14, 14, 14);

  if (wallpaper) {
    // Vraćena nativna Scriptable ekspozicija pozadine s integriranim zatamnjenjem
    let ctx = new DrawContext();
    ctx.size = wallpaper.size;
    ctx.respectScreenScale = true;
    ctx.drawImageInRect(wallpaper, new Rect(0, 0, wallpaper.size.width, wallpaper.size.height));
    
    // Zatamnjenje sloja pozadine za maksimalnu vidljivost
    ctx.setFillColor(new Color("#000000", 0.60)); 
    ctx.fillRect(new Rect(0, 0, wallpaper.size.width, wallpaper.size.height));
    
    w.backgroundImage = ctx.getImage();
  } else {
    w.backgroundColor = new Color("#05070c");
  }

  // 1. TOP SECTION (Samo na Large veličini)
  if (!isMedium) {
    w.addSpacer(6); // Mali odmak od samog gornjeg ruba
    let standingsCard = w.addStack();
    standingsCard.layoutVertically();
    standingsCard.backgroundColor = CONST_THEME.glass; 
    standingsCard.borderWidth = 1;
    standingsCard.borderColor = CONST_THEME.border;
    standingsCard.cornerRadius = 16;
    standingsCard.setPadding(12, 14, 12, 14);

    let topDrivers = data.standings.slice(0, 5);
    topDrivers.forEach((s, index) => {
      let row = standingsCard.addStack();
      row.centerAlignContent();
      
      let tFullName = s.Constructors[0]?.name || "";
      let cId = s.Constructors[0]?.constructorId || "";
      let tColor = TEAM_COLORS[tFullName] || TEAM_COLORS[cId] || "#ffffff";
      
      let accent = row.addStack();
      accent.size = new Size(4, 20); 
      accent.backgroundColor = new Color(tColor);
      accent.cornerRadius = 1.5;
      
      row.addSpacer(8);
      
      let textStack = row.addStack();
      textStack.layoutVertically();
      
      let driverRow = textStack.addStack();
      driverRow.centerAlignContent();
      
      let code = s.Driver.code || s.Driver.familyName.substring(0, 3).toUpperCase();
      let dCode = driverRow.addText(`${index + 1}. ${code}`);
      dCode.font = Font.boldMonospacedSystemFont(12); 
      dCode.textColor = Color.white();
      
      driverRow.addSpacer(6);
      let flag = driverRow.addText(DRIVER_FLAGS[code] || "🏁");
      flag.font = Font.systemFont(11);
      
      let teamShort = (TEAM_NAMES[cId] || tFullName).toUpperCase().replace("F1 TEAM", "").replace("RACING", "").replace("AMG", "").trim();
      let teamText = textStack.addText(teamShort);
      teamText.font = Font.mediumSystemFont(9);
      teamText.textColor = Color.white();
      teamText.textOpacity = 0.45; 
      teamText.lineLimit = 1;
      
      row.addSpacer();
      
      let pts = row.addText(s.points);
      pts.font = Font.blackMonospacedSystemFont(12);
      pts.textColor = Color.white();

      if (index < topDrivers.length - 1) {
        standingsCard.addSpacer(3);
        let lineRow = standingsCard.addStack();
        lineRow.layoutHorizontally();
        lineRow.addSpacer(6); 
        
        let line = lineRow.addStack();
        line.size = new Size(240, 0.5); 
        line.backgroundColor = new Color("#ffffff", 0.06); 
        
        lineRow.addSpacer(6); 
        standingsCard.addSpacer(3);
      }
    });
    
    // Kontrolirani fiksni razmak između gornje i donje kartice
    w.addSpacer(10); 
  }

  // 2. BOTTOM CARD
  let coreCard = w.addStack();
  coreCard.layoutHorizontally();
  coreCard.centerAlignContent();
  coreCard.backgroundColor = CONST_THEME.glass; 
  coreCard.borderWidth = 1;
  coreCard.borderColor = CONST_THEME.border;
  coreCard.cornerRadius = 16;
  coreCard.setPadding(12, 14, 12, 14);

  let leftSide = coreCard.addStack();
  leftSide.layoutVertically();
  leftSide.spacing = 3;
  
  let race = data.race?.raceName || "NEXT GRAND PRIX";
  let raceText = leftSide.addText(race.toUpperCase().replace("GRAND PRIX", "GP"));
  raceText.font = Font.blackSystemFont(isMedium ? 16 : 15); 
  raceText.textColor = Color.white();
  
  let loc = `${data.race?.Circuit?.Location?.locality || ""}, ${data.race?.Circuit?.Location?.country || ""}`;
  let locText = leftSide.addText(loc);
  locText.font = Font.mediumSystemFont(10);
  locText.textColor = Color.white();
  locText.textOpacity = 0.4;

  leftSide.addSpacer(4);

  let qTime = data.race.Qualifying?.time ? data.race.Qualifying.time.substring(0, 5) : "16:00";
  let rTime = data.race.time ? data.race.time.substring(0, 5) : "15:00";

  addSessionRow(leftSide, "timer", "QUALY", qTime);
  addSessionRow(leftSide, "flag.checkered.2.crossed", "RACE", rTime);

  leftSide.addSpacer(4);

  let raceDate = new Date(data.race.date + "T" + (data.race.time || "12:00:00Z"));
  let days = Math.floor((raceDate - new Date()) / (1000 * 60 * 60 * 24));
  
  let countdownBadge = leftSide.addStack();
  countdownBadge.backgroundColor = CONST_THEME.accent;
  countdownBadge.cornerRadius = 5;
  countdownBadge.setPadding(3, 8, 3, 8);
  let cd = countdownBadge.addText(days > 0 ? `${days} DAYS TO GO` : "RACE LIVE NOW");
  cd.font = Font.blackSystemFont(9);
  cd.textColor = Color.white();

  coreCard.addSpacer();

  let circuitKey = data.race?.Circuit?.circuitId?.toLowerCase();
  let mapUrl = data?.circuits?.direct_circuit_maps?.[circuitKey];
  if (mapUrl) {
    let trackImg = await fetchImage(mapUrl);
    if (trackImg) {
      let mapContainer = coreCard.addStack();
      mapContainer.size = isMedium ? new Size(140, 100) : new Size(145, 105);
      mapContainer.centerAlignContent();
      
      let finalMap = mapContainer.addImage(trackImg);
      finalMap.imageOpacity = 0.90;
    }
  }

  // Točno izračunat odmak koji sprječava bježanje footera na dno ekrana
  w.addSpacer(isMedium ? 4 : 8);

  // 3. COMBINED FOOTER ROW
  let footerRow = w.addStack();
  footerRow.centerAlignContent();
  
  footerRow.addSpacer(8);
  
  let f1Title = footerRow.addText("F1");
  f1Title.font = Font.blackSystemFont(9);
  f1Title.textColor = CONST_THEME.accent;
  
  footerRow.addSpacer(3);
  
  let dashTitle = footerRow.addText("PRO");
  dashTitle.font = Font.boldSystemFont(8);
  dashTitle.textColor = Color.white();
  dashTitle.textOpacity = 0.60;
  
  footerRow.addSpacer(); 
  
  let signStack = footerRow.addStack();
  signStack.centerAlignContent();
  
  let p1 = signStack.addText("BY ZER");
  p1.font = Font.regularMonospacedSystemFont(7.5);
  p1.textColor = Color.white();
  p1.textOpacity = 0.65; 
  
  let p2 = signStack.addText("OO7");
  p2.font = Font.regularMonospacedSystemFont(7.5);
  p2.textColor = CONST_THEME.accent; 
  p2.textOpacity = 0.55;
  
  let p3 = signStack.addText("EVEN");
  p3.font = Font.regularMonospacedSystemFont(7.5);
  p3.textColor = Color.white(); 
  p3.textOpacity = 0.55;
  
  footerRow.addSpacer(8);

  return w;
}

function addSessionRow(container, icon, label, time) {
  let stack = container.addStack();
  stack.centerAlignContent();
  
  let img = stack.addImage(SFSymbol.named(icon).image);
  img.imageSize = new Size(10, 10);
  img.tintColor = CONST_THEME.accent;
  
  stack.addSpacer(5);
  
  let lbl = stack.addText(`${label}:`);
  lbl.font = Font.boldSystemFont(9);
  lbl.textColor = Color.white();
  lbl.textOpacity = 0.4;
  
  stack.addSpacer(4);
  
  let t = stack.addText(time);
  t.font = Font.boldMonospacedSystemFont(9);
  t.textColor = Color.white();
}

// ======================================================

// RUNNER
// ======================================================
async function run(){

  const data =
    await loadF1Data();

  const news =
    await loadNewsData();

  const wallpaper =
    await loadWallpaper();

  if(config.runsInWidget){

    const widget =
      await createWidget(
        data,
        wallpaper
      );

    Script.setWidget(widget);

  } else {

    const html =
      generateHTML(
        data,
        news
      );

    const web =
      new WebView();

    await web.loadHTML(html);

    await web.present();

  }

  Script.complete();
}

await run();
