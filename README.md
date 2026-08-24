# PULSSI

PULSSI on VAIMEA LABin pelkistetty sivilisaation virtojen kojelauta. Se seuraa tietoliikennettä, lentoliikennettä, merirahtia, sähkövirtaa ja energiavirtaa ilman uutisia.

Mittarit ovat rajattuja havaintoikkunoita, eivät koko maailman täydellisiä kokonaislukuja. Jokainen näkymä kertoo siksi myös lähteen ja seurannan laajuuden.

## Päivitys

GitHub Actions kerää uuden snapshotin neljä kertaa vuorokaudessa. Päivän viimeinen havainto tallentuu `data/history`-hakemistoon ja jokainen ajo erikseen `data/observations`-hakemistoon.

## Lähteet

- Cloudflare Radar: maailman HTTP-liikenteen tuntisarja
- OpenSky Network: havaitut ilmassa olevat ilma-alukset
- IMF PortWatch / HDX: valittujen satamien seitsemän päivän satamakäynti-indeksi
- Fraunhofer Energy-Charts, Elexon ja Brasilian ONS: Saksan, Ison-Britannian ja Brasilian sähkökuormat. Geometrinen yhdistelmä antaa jokaiselle verkolle saman painon.
- Energiavirtaindeksi: JODI Oilin öljyntuotanto, jalostamojen syöttö ja vienti muodostavat öljyn hitaan ankkurin. JODI Gasin kaasuntuotanto, putkivienti ja LNG-vienti muodostavat kaasun ankkurin. Hormuzin tankkerivirta toimii painoltaan rajattuna nopeana häiriösignaalina öljyindeksin sisällä. Öljyn maailman energiaosuus on 40 % ja kaasun 30 %; puuttuvat hiili ja muut polttoaineet näkyvät 70 %:n kattavuutena eikä niiden painoa teeskennellä havaituksi. Sähkövirta ei kuulu energiavirtaindeksiin.

