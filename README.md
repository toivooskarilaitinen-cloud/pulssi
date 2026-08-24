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
- IMF PortWatch / straits.live: Hormuzinsalmen havaittujen tankkerikulkujen seitsemän päivän keskiarvo

