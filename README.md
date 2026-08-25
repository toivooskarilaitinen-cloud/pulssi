# PULSSI

PULSSI on VAIMEA LABin pelkistetty sivilisaation virtojen kojelauta. Se seuraa tietoliikennettä, lentoliikennettä, merirahtia, sähkövirtaa ja energiavirtaa ilman uutisia.

Mittarit ovat rajattuja havaintoikkunoita, eivät koko maailman täydellisiä kokonaislukuja. Jokainen näkymä kertoo siksi myös lähteen ja seurannan laajuuden.

## Päivitys

GitHub Actions kerää uuden snapshotin neljä kertaa vuorokaudessa. Päivän viimeinen havainto tallentuu `data/history`-hakemistoon ja jokainen ajo erikseen `data/observations`-hakemistoon.

## Lähteet

- Cloudflare Radar: suhteellinen HTTP-aktiivisuus verrattuna edellisten päivien samaan UTC-tuntiin; ei raaka maailman pyyntömäärä
- OpenSky Network: havaitut ilmassa olevat ilma-alukset; paikallinen vertailutaso suosii samaa viikonpäivää ja UTC-tuntia
- IMF PortWatch / HDX: valittujen satamien seitsemän päivän satamakäynti-indeksi
- Fraunhofer Energy-Charts, Elexon ja Brasilian ONS: Saksan, Ison-Britannian ja Brasilian sähkökuormat. Geometrinen yhdistelmä antaa jokaiselle verkolle saman painon.
- Energiavirtaindeksi on hidas taustatila, ei reaaliaikainen pulssi. JODI Oilin öljyntuotanto, jalostamojen syöttö ja vienti muodostavat öljyn kuukausiankkurin. JODI Gasin kaasuntuotanto, putkivienti ja LNG-vienti muodostavat kaasun kuukausiankkurin. Hormuzin tankkerivirta toimii painoltaan rajattuna nopeana häiriösignaalina. Käyttöliittymä näyttää osien eri päivitysajankohdat, kattavuuden ja luottamuksen.

Menetelmä v0.6 luokittelee sekä tavallista hiljaisemmat että tavallista vilkkaammat poikkeamat symmetrisesti. Havaintohistoriaa verrataan ensisijaisesti samaan viikonpäivään ja UTC-tuntiin, toissijaisesti samaan UTC-tuntiin.
