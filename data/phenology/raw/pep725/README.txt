IMPORTANT DETAILS FOR THE USE OF PEP725 DATASETS
 
Legal Notice:
-----------------------------
The PEP725 project management team, as operators of website and database, requires all
Users who have access to PEP725 data to abide by the terms and conditions of our PEP725_Data_Use_Policy
(https://pep725.eu/pep725_data_use_policy/)
 
In particular, compliance with the PEP725 Data Attribution Policy should be noted at this point:
 
a) Acknowledgement: The following acknowledgement must be included in either the
main text or Acknowledgments section of all publications using PEP725 data.
Acknowledgment: 'Data were provided by the members of the PEP725 project'
b) Bibliographic information should be provided to the PEP725 project management
(pep725@geosphere.at) for all manuscripts using PEP725 data immediately after their
publication
c) Citation: All PEP725 data sets must be cited following the example below:
Templ, B., Koch, E., Bolmgren, K., Ungersböck, M., Paul, A., Scheifinger, H., et al.
(2018). Pan European Phenological database (PEP725): a single point of access for
European data. Int. J. Biometeorology. doi: 10.1007/s00484-018-1512-8
Data set accessed YYYY-MM-DD at https://pep725.eu
 
The Dataset: 
-----------------------------
This dataset was provided by the Pan European Phenology Project (pep725.eu)
	and collected by the following project members:
 
provider_id Phenological Network
          7 COST725 member Luxembourg
         13 COST725 member France
         14 COST725 member Spain
        101 PEP725 member DWD
        201 PEP725 member meteo.si
        301 PEP725 member ZAMG / GeoSphere Austria
        501 PEP725 member METEOSCHWEIZ
        601 PEP725 member SHMU Slovakia
       1401 PEP725 member SMC-Meteocat
       1402 PEP725 member AEMET
       1802 PEP725 member Naturens kalender
       2101 PEP725 member DHMZ
       2201 PEP725 member CRI
       2601 PEP725 member FHMZBIH
       2701 PEP725 member ZHMS Crna Gora

 Dataset retrieved 2026-07-01

Dataset description:
-----------------------------
The data is provided in csv format, with ';' as separator and '\r\n' as newline 
character (Windows notation). For processing reasons, larger database extracts are 
summarized to 400 000 observations each with a single header line. All records have been
sorted by age, starting with the oldest.
If there are any questions about the handling or interpretation of the data, please send
them to pep725@geosphere.at.
Below the individual columns in detail, additional information is also available on our
homepage (https://pep725.eu)
 
column        description
s_id          Unique station identifyer, mean location of all plants observed at one point
provider_id   Unique ID of the collecting Phenological Network, see table above
lon			 geogr. longitude of the station (WGS84)
lat           geogr. latitude of the station (WGS84)
alt           Altitude of the station if reported from the network (-9999 missing value indicator)
alt_dem       As we do not have altitude information for all station we provide, as additional
              information, the sea level derived from digital elevation models (DEM) for the 
              given coordinates. Main source is the Aster Global Digital Elevation Model V1 2009
              (ASTER GDEM is a product of METI and NASA) accessed through the geonames.org webservice.
              For high latitudes USGS GTOPO30 was used as second source. Please note: high differences
              between alt and alt_dem MIGHT indicate problems in the station description - but in 
              mountains or on the coast little inaccuracies of the coordinates could lead to huge 
              deviations of the DEM altitude. We try to identify and correct those stations but that's
              a very time consuming task and not always possible. For now we recommend to handle stations
              with a difference between alt and alt_dem greater 50m (~ 3 * Mean Absolute Deviation)
              with appropriate care
gss_id        Unique plant identifyer, see also https://pep725.eu/pep725-plants/
genus         Plant genus
species       Plant species (if avalilable)
subspecies    Plant subspecies or cultivar (if available)
phase_id      Plant growing phase, from 0-99 it corresponds to the BBCH scale, above there are additional stages.
              The complete list you can find below and at https://pep725.eu/pep725-phases/ 
year          Year of observation
day           Day of Year (DOY), 1..First January, ...
date	       Date of observation, same as Year/Day for your convenience
cult_season   Season of cultivation: 0..not applicable, 1..summer cereals - sowing in spring, 2..winter cereals - sowing in autumn
license_short Abbreviation of the data licence - further details in the Licences section below

Definition of growing stages:
-----------------------------
Below the list of already defined phenological phases of PEP725.
Please note that some phases were only provided for future expansion of the programme.
phase_id's up to 99 correspond to the well known BBCH-scale. From 100 upwards you will find additional phases which are not covered in the BBCH system.

phase_id description
       0 Dry seed (seed dressing takes place at stage 00), P, V: Winter dormancy or resting period
       1 Beginning of seed imbibition, P, V: Beginning of bud swelling
       3 Seed imbibition complete, P, V: End of bud swelling
       5 Radicle (root) emerged from seed, P, V: Perennating organs forming roots
       6 Elongation of radicle, formation of root hairs and /or lateral roots
       7 G: Coleoptile emerged from caryopsis, D, M: Hypocotyl with cotyledons or shoot breaking through seed coat, P, V: Beginning of sprouting or bud breaking
       8 D: Hypocotyl with cotyledons growing towards soil surface, P, V: Shoot growing towards soil surface
       9 G: Emergence: Coleoptile breaks through soil surface, D, M: Emergence: Cotyledons break through soil surface(except hypogeal germination),D, V: Emergence: Shoot/leaf breaks through soil surface, P: Bud shows green tips
      10 G: First true leaf emerged from coleoptile, D, M: Cotyledons completely unfolded, P: First leaves separated
      11 First true leaf, leaf pair or whorl unfolded, P: First leaves unfolded
      12 2 true leaves, leaf pairs or whorls unfolded
      13 3 true leaves, leaf pairs or whorls unfolded
      14 4 true leaves, leaf pairs or whorls unfolded
      15 5 true leaves, leaf pairs or whorls unfolded
      16 6 true leaves, leaf pairs or whorls unfolded
      17 7 true leaves, leaf pairs or whorls unfolded
      18 8 true leaves, leaf pairs or whorls unfolded
      19 9 or more true leaves, leaf pairs or whorls unfolded
      21 First side shoot visible, G: First tiller visible
      22 2 side shoots visible, G: 2 tillers visible
      23 3 side shoots visible, G: 3 tillers visible
      24 4 side shoots visible, G: 4 tillers visible
      25 5 side shoots visible, G: 5 tillers visible
      26 6 side shoots visible, G: 6 tillers visible
      27 7 side shoots visible, G: 7 tillers visible
      28 8 side shoots visible, G: 8 tillers visible
      29 9 or more side shoots visible, G: 9 or more tillers visible
      30 Onset of height growth (e.g. Pinus, Picea)
      31 Stem (rosette) 10% of final length (diameter), G: 1 node detectable
      32 Stem (rosette) 20% of final length (diameter), G: 2 nodes detectable
      33 Stem (rosette) 30% of final length (diameter), G: 3 nodes detectable
      34 Stem (rosette) 40% of final length (diameter), G: 4 nodes detectable
      35 Stem (rosette) 50% of final length (diameter), G: 5 nodes detectable
      36 Stem (rosette) 60% of final length (diameter), G: 6 nodes detectable
      37 Stem (rosette) 70% of final length (diameter), G: 7 nodes detectable
      38 Stem (rosette) 80% of final length (diameter), G: 8 nodes detectable
      39 Maximum stem length or rosette diameter reached, G: 9 or more nodes detectable, end of height growth (e.g. Pinus, Picea
      40 Harvestable vegetative plant parts or vegetatively propagated organs begin to develop
      41 G: Flag leaf sheath extending
      43 Harvestable vegetative plant parts or vegetatively propagated organs have reached 30% of final size, G: Flag leaf sheath just visibly swollen (mid-boot)
      45 Harvestable vegetative plant parts or vegetatively propagated organs have reached 50% of final size, G: Flag leaf sheath swollen (late-boot)
      47 Harvestable vegetative plant parts or vegetatively propagated organs have reached 70% of final size, G: Flag leaf sheath opening
      48 Maximum of total tuber mass reached, tubers detach easily from stolons, skin set not yet complete (skin easily removable with thumb)
      49 Harvestable vegetative plant parts or vegetatively propagated organs have reached final size, G: First awns visible, Skinset complete
      50 Flower buds present, still enclosed by leaves (oilseed rape)
      51 Inflorescence or flower buds visible, G: Beginning of heading
      52 G:20% of inflorescence emerged
      53 G:30% of inflorescence emerged
      54 G:40% of inflorescence emerged
      55 First individual flowers visible (still closed), G: Half of inflorescence emerged (middle of heading)
      56 G:60% of inflorescence emerged
      57 G:70% of inflorescence emerged
      58 G:80% of inflorescence emerged
      59 First flower petals visible (in petalled forms), G: Inflorescence fully emerged (end of heading)
      60 Start of flowering: first flowers open (sporadically)
      61 Start of flowering: 10% of flowers open
      62 20% of flowers open
      63 30% of flowers open, maize: male beginning of pollen shedding, female: tips of stigmata visible
      64 40% of flowers open
      65 Full flowering: 50% of flowers open, first petals may be fallen
      67 Flowering finishing: majority of petals fallen or dry
      69 End of flowering: fruit set visible
      71 10% of fruits have reached final size or fruit has reached 10% of final size, G: Caryopsis watery ripe
      72 20% of fruits have reached final size or fruit has reached 20% of final size
      73 30% of fruits have reached final size or fruit has reached 30% of final size, G: Early milk
      74 40% of fruits have reached final size or fruit has reached 40% of final size
      75 50% of fruits have reached final size or fruit has reached 50% of final size, G: Milky ripe, medium milk
      76 60% of fruits have reached final size or fruit has reached 60% of final size
      77 70% of fruits have reached final size or fruit has reached 70% of final size, G: Late milk
      78 80% of fruits have reached final size or fruit has reached 80% of final size
      79 Nearly all fruits have reached final size
      80 olive: fruit deep green colour becomes lightgreen, yellowish
      81 Beginning of ripening or fruit colouration
      83 G: early dough stage
      85 Advanced ripening or fruit colouration, G: Soft dough stage
      87 Fruit begins to soften (species with fleshy fruit), fruit ripe for picking
      89 Fully ripe: fruit shows fully-ripe colour, beginning of fruit abscission
      91 P: Shoot development completed, foliage still green, grapevine: after harvest, end of wood maturation
      93 Beginning of leaf-fall
      95 50% of leaves fallen
      97 End of leaf fall, plants or above ground parts dead or dormant, P Plant resting or dormant
      99 Harvested product (post-harvest or storage treatment is applied at stage 99)
     100 start of harvest
     109 end of harvest
     111 first cut for silage winning
     115 first cut for silage winning (=> 50% of the area)
     119 end of the first cut for silage winning (=> 90% of the area)
     131 first cut for hay winning
     135 first cut for hay winning (=> 50% of the area)
     139 end of first cut for hay winning (=> 90% of the area)
     140 second cut for hay winning, aftermath
     151 start of  harvest for silage (corn, grass)
     161 start of Corn - cob - mix harvest for silage
     182 25% of the permanent grassland shows fresh green
     200 autumnal leaf colouring: first discoloured leaves (sporadically)
     201 autumnal leaf colouring: leaves beginn to discolour (>=10%)
     202 autumnal leaf colouring >=20%
     203 autumnal leaf colouring >=30%
     204 autumnal leaf colouring >=40%
     205 autumnal leaf colouring >=50%
     206 autumnal leaf colouring >=60%
     207 autumnal leaf colouring >=70%
     208 autumnal leaf colouring >=80%
     209 end of autumnal leaf colouring: nearly all leaves are discoloured (>=90%)
     210 autumnal leaf fall: first fallen leaves (sporadically)
     212 autumnal leaf fall: >=20% of leaves fallen
     213 autumnal leaf fall: >=30% of leaves fallen
     214 autumnal leaf fall: >=40% of leaves fallen
     216 autumnal leaf fall: >=60% of leaves fallen
     217 autumnal leaf fall: >=70% of leaves fallen
     218 autumnal leaf fall: >=80% of leaves fallen
     223 Leaf unfolding (>=50%)
     250 Grapevine bleeding, pruned grapes start to loss water from the cuts
     251 sap exudation (birch trees)
     380 The first fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     381 >=10% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     382 >=20% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     383 >=30% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     384 >=40% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     385 >=50% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     386 >=60% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     387 >=70% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     388 >=80% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).
     389 >=90% of the fruits on the tree or in the crown are ripe (they have changed colour, dried out, become dehiscent or fallen off).

Licences:
-------------------------+ ----------------------------
 Until 2025, the PEP725 dataset was licensed exclusively for non-commercial use.
 In order to be able to offer data that uses a different licence, the database was expanded accordingly.
 Below are the different licence models under which the data is passed on. Please check whether you can agree to the licence conditions!
* CC BY 4.0
  You are free to: Share & Adapt but you have to give credit to the project. 
  More info https://creativecommons.org/licenses/by/4.0/

* CC BY-NC 4.0
  You are free to: Share & Adapt but you have to give credit to the project and you may NOT use the material for commercial purposes! 
  More info https://creativecommons.org/licenses/by-nc/4.0/

* CC BY-SA 2.0
  You are free to: Share & Adapt but you have to give credit to the project, all derived works have to be shared under the same license! 
  More info https://creativecommons.org/licenses/by-sa/2.0/

* CC0 1.0
  Those data are released in the public domain without any rights reserved. 
  More info https://creativecommons.org/publicdomain/zero/1.0/

* LO 2.0
  Licence Ouverte  V2.0. This license is compatible with Creative Commons Attribution (CC-BY) - please inform yoursef about possible
 differences in the license terms.
  More info https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf

Some of the French datasets were downloaded from the TEMPO data portal https://tempo.pheno.fr/ 

Maury, Olivier; Quidoz, Marie-Claude; Garcia de Cortazar Atauri, Iñaki; Chuine, Isabelle; 
El Hasnaoui, Mohamed; Tromel, Louis, 2023, “Portail de données phénologiques du réseau 
TEMPO / TEMPO Data Portal”, https://doi.org/10.57745/NQ9HRV, Recherche Data Gouv, V1

For these, we have more information about the data source and how we adapted the original data into PEP725 format
Please note that during the import process from the TEMPO portal, some plant and/or growth phase selections were made. In individual cases,
 observation phases were also changed and adapted to the PEP725 specifications.
Below you can find additional information about the changes that were made (currently being compiled). 
provider_id: 1301: ODS Tela Botanica https://pep725.eu/dataset_description_1301/
provider_id: 1302: Phénoclim CREA Mont-Blanc https://pep725.eu/dataset_description_1302/
provider_id: 1303: AgroClim Pheno
provider_id: 1304: Forêt
