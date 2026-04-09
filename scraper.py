const JSON_URL = "https://raw.githubusercontent.com/zeroOSeven-AI/News/main/sportske.json"

async function createWidget() {
  let widget = new ListWidget()
  widget.backgroundColor = new Color("#121212")
  
  try {
    let req = new Request(JSON_URL)
    // Dodajemo cache-breaker da uvijek vuče najnovije s GitHuba
    req.method = "GET"
    let items = await req.loadJSON()
    
    let header = widget.addText("SPORTSKE NOVOSTI")
    header.textColor = new Color("#ed1c24")
    header.font = Font.boldSystemFont(13)
    widget.addSpacer(12)

    // Uzmi prve 3 vijesti
    for (let i = 0; i < 3; i++) {
      if (!items[i]) break
      let item = items[i]
      
      let row = widget.addStack()
      row.centerAlignContent()
      row.url = item.link

      // Slika
      if (item.image && item.image.startsWith('http')) {
        try {
          let imgReq = new Request(item.image)
          let img = await imgReq.loadImage()
          let wImg = row.addImage(img)
          wImg.imageSize = new Size(55, 38)
          wImg.cornerRadius = 4
          row.addSpacer(10)
        } catch(e) {}
      }

      // Naslov
      let title = row.addText(item.title)
      title.textColor = Color.white()
      title.font = Font.mediumSystemFont(11)
      title.lineLimit = 2
      
      widget.addSpacer(10)
    }
  } catch(e) {
    let err = widget.addText("Provjeri repozitorij (Public?)")
    err.textColor = Color.gray()
    err.font = Font.systemFont(10)
  }
  
  return widget
}

if (config.runsInWidget) {
  Script.setWidget(await createWidget())
} else {
  (await createWidget()).presentMedium()
}
Script.complete()
