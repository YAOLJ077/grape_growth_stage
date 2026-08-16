var INDEX_ASSET = 'projects/glossy-essence-477012-s7/assets/weather_download_index_1951_gee_20parts';
var PART_START = 1;
var PART_END = 15;
var OUT_FOLDER = 'grape_phenology_era5_land_daily';

var ERA5 = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR');

var BANDS = [
  'temperature_2m',
  'temperature_2m_min',
  'temperature_2m_max',
  'dewpoint_temperature_2m',
  'total_precipitation_sum',
  'surface_pressure',
  'surface_solar_radiation_downwards_sum',
  'u_component_of_wind_10m',
  'v_component_of_wind_10m'
];

var SAMPLE_SCALE = 11132;

var fullIndex = ee.FeatureCollection(INDEX_ASSET);

var metaFields = [
  'weather_id',
  'gee_part',
  'gee_part_key',
  'country',
  'source',
  'site_id',
  'site_name',
  'lat',
  'lon',
  'alt_m',
  'year',
  'weather_start_date',
  'weather_end_date',
  'n_events',
  'bbch_list',
  'phenophase_list',
  'model_tier',
  'first_event_date',
  'last_event_date',
  'first_event_doy',
  'last_event_doy'
];

function oneSiteYearToDaily(row) {
  row = ee.Feature(row);

  var point = row.geometry();
  var start = ee.Date(ee.String(row.get('weather_start_date')));
  var end = ee.Date(ee.String(row.get('weather_end_date'))).advance(1, 'day');
  var meta = row.toDictionary(metaFields);

  return ERA5
    .select(BANDS)
    .filterDate(start, end)
    .map(function(image) {
      var values = image.reduceRegion({
        reducer: ee.Reducer.first(),
        geometry: point,
        scale: SAMPLE_SCALE,
        bestEffort: true,
        tileScale: 4
      });

      return ee.Feature(null, meta.combine(values).combine({
        weather_date: image.date().format('YYYY-MM-dd'),
        weather_year: image.date().get('year'),
        weather_month: image.date().get('month'),
        weather_doy: image.date().getRelative('day', 'year').add(1)
      }));
    });
}

function buildDailyWeather(partId) {
  var index = fullIndex.filter(ee.Filter.eq('gee_part', partId));
  var rowList = index.toList(index.size());
  var nestedDaily = ee.List.sequence(0, index.size().subtract(1)).map(function(i) {
    return oneSiteYearToDaily(ee.Feature(rowList.get(i)));
  });

  print('PART_ID', partId);
  print('Rows', index.size());
  print('Input example', index.first());

  return ee.FeatureCollection(nestedDaily).flatten();
}

for (var partId = PART_START; partId <= PART_END; partId++) {
  var dailyWeather = buildDailyWeather(partId);
  var partLabel = 'part_' + String(partId).padStart(2, '0') + '_of_20';
  var description = 'era5_land_daily_grape_1951_' + partLabel;

  print('Output example ' + partLabel, dailyWeather.first());
  print('Output rows ' + partLabel, dailyWeather.size());

  Export.table.toDrive({
    collection: dailyWeather,
    description: description,
    folder: OUT_FOLDER,
    fileNamePrefix: description,
    fileFormat: 'CSV',
    selectors: metaFields.concat([
      'weather_date',
      'weather_year',
      'weather_month',
      'weather_doy'
    ]).concat(BANDS)
  });
}
