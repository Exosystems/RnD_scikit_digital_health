// Copyright (c) 2021. Pfizer Inc. All rights reserved.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <float.h>
/* for reading from ActiGraph files */
//#include <zip.h>

/*
======================================
GENERAL
======================================
*/
#define SECMIN 60
#define SECHOUR 3600
#define DAYSEC 86400.f

#define MAX_DAYS 25

/* keep track of windowing information */
typedef struct {
    long n;  /* number of windows */
    long *bases;  /* base hours for windowing */
    long *periods;  /* lengths of windows */
    long *i_start;  /* index for start array */
    long *i_stop;  /* index for end array */
} Window_t;

/* match time_t from utility.f95 */
typedef struct {
    long hour;
    long min;
    long sec;
    long msec;  /* NOTE that this is an integer! ex. 0.500 -> 500 */
} Time_t;

/* 
get_day_indexing(fs, dtime, mxd, n, bases, periods, block_n, max_n, block_samples, starts, 
    i_starts, stops, i_stops)
*/
extern void get_day_indexing(double *, Time_t *, long *, long *, long *, long *, long *, long *,
    long *, long *, long *, long *, long *);

/*
======================================
AXIVITY
======================================
*/
typedef struct {
    long deviceId;
    long sessionId;
    int nblocks;
    int8_t axes;
    int16_t count;
    double tLast;
    int N;
    double frequency;
    long Nwin;  /* number of windows (bases/periods) */
    long max_days;  /* max days set for the size of the starts/stops array */
    long n_bad_blocks;  /* number of blocks with nonzero checksums */
} AX_Info_t;

typedef struct {
    double *imu;
    double *temp;
    double *ts;
    long *day_starts;
    long *day_stops;
} AX_Data_t;

typedef enum {
    AX_READ_E_NONE = 0,
    AX_READ_E_BAD_HEADER = 1,
    AX_READ_E_MISMATCH_N_AXES = 2,
    AX_READ_E_INVALID_BLOCK_SAMPLES = 3,
    AX_READ_E_BAD_AXES_PACKED = 4,
    AX_READ_E_BAD_PACKING_CODE = 5,
    AX_READ_E_BAD_CHECKSUM = 6,
} Read_Cwa_Error_t;

extern void axivity_read_header(long *, char[], AX_Info_t *, int *);
extern void axivity_read_block(AX_Info_t *, long *, double *, double *, double *, long *, long *,
    long *, long *, long *, long *, int *);
extern void axivity_close(AX_Info_t *);

/*
======================================
GENEACTIV
======================================
*/
#define GN_SAMPLES 300
#define GN_SAMPLESf 300.0f

#define GN_READLINE fgets(buff, 255, fp)

#define GN_DATE_YEAR(_v)  strtol(&_v[10], NULL, 10)
#define GN_DATE_MONTH(_v) strtol(&_v[15], NULL, 10)
#define GN_DATE_DAY(_v)   strtol(&_v[18], NULL, 10)
#define GN_DATE_HOUR(_v)  strtol(&_v[21], NULL, 10)
#define GN_DATE_MIN(_v)   strtol(&_v[24], NULL, 10)
#define GN_DATE_SEC(_v)   strtol(&_v[27], NULL, 10)
#define GN_DATE_MSEC(_v)  strtol(&_v[30], NULL, 10)


/* READ ERRORS */
typedef enum {
    GN_READ_E_NONE,  /* no error return value */
    GN_READ_E_BLOCK_TIMESTAMP,  /* issue reading timestamp from block */
    GN_READ_E_BLOCK_FS,  /* block FS does not match header fs */
    GN_READ_E_BLOCK_FS_WARN,  /* warning about FS */
    GN_READ_E_BLOCK_DATA,  /* error reading block data */
    GN_READ_E_BLOCK_DATA_3600  /* data is less than 3600 characters */
} Read_Bin_Error_t;


/* Information structures */
typedef struct {
    double fs;  /* sampling frequency */
    int fs_err;  /* keep track of differing values of fs during block reading */
    double gain[3];  /* raw accel value gain for converting to g */
    double offset[3];  /* raw accel value offset for converting to g */
    double volts;
    double lux;
    long npages;
    long max_n;
} GN_Info_t;

typedef struct {
    double *acc;
    double *light;
    double *temp;
    double *ts;
    long *day_starts;
    long *day_stops;
} GN_Data_t;


int geneactiv_read_header(FILE *fp, GN_Info_t *info);
int geneactiv_read_block(FILE *fp, Window_t *w_info, GN_Info_t *info, GN_Data_t *data);

/*
======================================
ACTIGRAPH
======================================
*/

#define AG_DBGPRINT(a) if (info->debug) fprintf(stdout, a "\n");
#define AG_DBGPRINT1(a, b) if (info->debug) fprintf(stdout, a "\n", b);

/* READ ERRORS */
typedef enum {
    AG_READ_E_NONE,  /* no error return value */
    AG_READ_E_INFO_STAT,  /* Error getting the file info stats */
    AG_READ_E_INFO_OPEN,  /* Error getting the file info */
    AG_READ_E_LOG_OPEN,  /* Error getting the log file from the zip archive */
    AG_READ_E_LOG_MULTIPLE_ACTIVITY_TYPES,  /* multiple activity types in the log */
    AG_READ_E_OLD_ACTIVITY_OPEN,  /* error opening an old activity file */
    AG_READ_E_OLD_LUX_OPEN,  /* error opening an old format lux file */
    AG_READ_E_MALLOC  /* error malloc'ing some data */
} Read_Gt3x_Error_t;

/* Information structures */
typedef struct {
    int debug;  /* bool */
    int is_old_version;  /* boolean if the file is using the old format */
    int samples;  /* number of samples in the file */
    int n_days;  /* to keep track of the number of days */
    int ndi;  /* n_days index tracker */
    int current_sample;  /* track the current sample in arrays */
    int open_err;  /* error saving for the zip archive */
} AG_Info_t;

typedef struct {
    int major;
    int minor;
    int build;
} AG_Version_t;

typedef struct {
    char serial[14];
    int sample_rate;
    double start_time;
    double stop_time;
    double last_sample_time;
    double download_time;
    double accel_scale;
    AG_Version_t firmware;
} AG_SensorInfo_t;

typedef struct {
    double *ts;
    double *acc;
    double *lux;
    long *day_starts;
    long *day_stops;
} AG_Data_t;