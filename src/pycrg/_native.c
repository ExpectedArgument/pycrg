/*
 * Native bindings for the vendored OpenCRG C API.
 *
 * This module is private: pycrg.api wraps it with handle objects that track
 * whether data sets and contact points are still alive. Functions here take
 * raw OpenCRG ids and do not check them beyond what the C library does.
 *
 * All calls into the C library are made with the GIL held. The library keeps
 * global state (data set and contact point tables, message settings), so the
 * GIL serialises access to it.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <math.h>
#include <string.h>

#include "crgBaseLibPrivate.h"

/* added to the vendored library by tools/vendor_patches */
extern int crgPortGetMaxWarnMsgs( void );

static PyObject* g_error = NULL;            /* pycrg.errors.OpenCRGError */
static PyObject* g_eval_error = NULL;       /* pycrg.errors.OpenCRGEvaluationError */

static PyObject* g_msg_handler = NULL;      /* Python callable receiving (level, text) */
static PyObject* g_calloc_callback = NULL;
static PyObject* g_realloc_callback = NULL;
static PyObject* g_free_callback = NULL;

/* ------------------------------------------------------------------------- */
/* helpers                                                                   */
/* ------------------------------------------------------------------------- */

static PyObject* py_bool( int ok ) {
    return PyBool_FromLong( ok ? 1 : 0 );
}

static PyObject* raise_error( const char* message ) {
    PyErr_SetString( g_error, message );
    return NULL;
}

static int parse_int( PyObject* obj, int* value ) {
    long result = PyLong_AsLong( obj );
    if ( result == -1 && PyErr_Occurred() )
        return 0;
    if ( result < INT_MIN || result > INT_MAX ) {
        PyErr_SetString( PyExc_OverflowError, "value does not fit into a C int" );
        return 0;
    }
    *value = ( int ) result;
    return 1;
}

static int parse_double( PyObject* obj, double* value ) {
    double result = PyFloat_AsDouble( obj );
    if ( result == -1.0 && PyErr_Occurred() )
        return 0;
    *value = result;
    return 1;
}

/* parse (int id, float a, float b) for the evaluation functions */
static int parse_eval_args( PyObject* const* args, Py_ssize_t nargs, const char* name, int* cp_id, double* a, double* b ) {
    if ( nargs != 3 ) {
        PyErr_Format( PyExc_TypeError, "%s() takes exactly 3 arguments (%zd given)", name, nargs );
        return 0;
    }
    return parse_int( args[0], cp_id ) && parse_double( args[1], a ) && parse_double( args[2], b );
}

/* ------------------------------------------------------------------------- */
/* callbacks from the C library                                              */
/* ------------------------------------------------------------------------- */

static int c_msg_bridge( int level, char* message ) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* handler = g_msg_handler;

    if ( handler != NULL ) {
        PyObject* text;
        PyObject* result = NULL;

        /* the message may be emitted while an exception is pending */
#if PY_VERSION_HEX >= 0x030C0000
        PyObject* pending = PyErr_GetRaisedException();
#else
        PyObject *exc_type, *exc_value, *exc_tb;
        PyErr_Fetch( &exc_type, &exc_value, &exc_tb );
#endif
        Py_INCREF( handler );

        text = PyUnicode_DecodeUTF8( message != NULL ? message : "", message != NULL ? ( Py_ssize_t ) strlen( message ) : 0,
                                     "backslashreplace" );
        if ( text != NULL ) {
            result = PyObject_CallFunction( handler, "iO", level, text );
            Py_DECREF( text );
        }
        if ( result == NULL )
            PyErr_WriteUnraisable( handler );
        else
            Py_DECREF( result );

        Py_DECREF( handler );
#if PY_VERSION_HEX >= 0x030C0000
        PyErr_SetRaisedException( pending );
#else
        PyErr_Restore( exc_type, exc_value, exc_tb );
#endif
    }

    PyGILState_Release( gil );
    return 0;
}

static void* c_calloc_bridge( size_t nmemb, size_t size ) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* result = NULL;
    void* ptr = NULL;

    if ( g_calloc_callback != NULL ) {
        result = PyObject_CallFunction( g_calloc_callback, "KK", ( unsigned long long ) nmemb, ( unsigned long long ) size );
        if ( result == NULL ) {
            PyErr_WriteUnraisable( g_calloc_callback );
        } else {
            if ( result != Py_None ) {
                ptr = PyLong_AsVoidPtr( result );
                if ( PyErr_Occurred() ) {
                    PyErr_WriteUnraisable( g_calloc_callback );
                    ptr = NULL;
                }
            }
            Py_DECREF( result );
        }
    }

    PyGILState_Release( gil );
    return ptr;
}

static void* c_realloc_bridge( void* ptr, size_t size ) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* result = NULL;
    PyObject* ptr_obj = NULL;
    void* out_ptr = NULL;

    if ( g_realloc_callback != NULL && ( ptr_obj = PyLong_FromVoidPtr( ptr ) ) != NULL ) {
        result = PyObject_CallFunction( g_realloc_callback, "OK", ptr_obj, ( unsigned long long ) size );
        Py_DECREF( ptr_obj );
        if ( result == NULL ) {
            PyErr_WriteUnraisable( g_realloc_callback );
        } else {
            if ( result != Py_None ) {
                out_ptr = PyLong_AsVoidPtr( result );
                if ( PyErr_Occurred() ) {
                    PyErr_WriteUnraisable( g_realloc_callback );
                    out_ptr = NULL;
                }
            }
            Py_DECREF( result );
        }
    }

    PyGILState_Release( gil );
    return out_ptr;
}

static void c_free_bridge( void* ptr ) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* result = NULL;
    PyObject* ptr_obj = NULL;

    if ( g_free_callback != NULL && ( ptr_obj = PyLong_FromVoidPtr( ptr ) ) != NULL ) {
        result = PyObject_CallFunction( g_free_callback, "O", ptr_obj );
        Py_DECREF( ptr_obj );
        if ( result == NULL )
            PyErr_WriteUnraisable( g_free_callback );
        else
            Py_DECREF( result );
    }

    PyGILState_Release( gil );
}

static int store_callback( PyObject* callback, PyObject** slot ) {
    if ( callback != Py_None && !PyCallable_Check( callback ) ) {
        PyErr_SetString( PyExc_TypeError, "callback must be callable or None" );
        return 0;
    }
    if ( callback == Py_None ) {
        Py_CLEAR( *slot );
    } else {
        Py_INCREF( callback );
        Py_XSETREF( *slot, callback );
    }
    return 1;
}

/* ------------------------------------------------------------------------- */
/* library and messages                                                      */
/* ------------------------------------------------------------------------- */

static PyObject* py_get_release_info( PyObject* self, PyObject* unused ) {
    return PyUnicode_FromString( crgGetReleaseInfo() );
}

static PyObject* py_mem_release( PyObject* self, PyObject* unused ) {
    crgMemRelease();
    Py_RETURN_NONE;
}

static PyObject* py_msg_set_level( PyObject* self, PyObject* arg ) {
    int level;
    if ( !parse_int( arg, &level ) )
        return NULL;
    crgMsgSetLevel( level );
    Py_RETURN_NONE;
}

static PyObject* py_msg_get_level( PyObject* self, PyObject* unused ) {
    return PyLong_FromLong( crgMsgGetLevel() );
}

static PyObject* py_msg_set_max_warn_msgs( PyObject* self, PyObject* arg ) {
    int max_no;
    if ( !parse_int( arg, &max_no ) )
        return NULL;
    crgMsgSetMaxWarnMsgs( max_no );
    Py_RETURN_NONE;
}

static PyObject* py_msg_get_max_warn_msgs( PyObject* self, PyObject* unused ) {
    return PyLong_FromLong( crgPortGetMaxWarnMsgs() );
}

static PyObject* py_msg_set_max_log_msgs( PyObject* self, PyObject* arg ) {
    int max_no;
    if ( !parse_int( arg, &max_no ) )
        return NULL;
    crgMsgSetMaxLogMsgs( max_no );
    Py_RETURN_NONE;
}

/* crgMsgIsPrintable() returns non-zero for printable levels (its header comment
   says the opposite, but the implementation is what counts) */
static PyObject* py_msg_is_printable( PyObject* self, PyObject* arg ) {
    int level;
    if ( !parse_int( arg, &level ) )
        return NULL;
    return py_bool( crgMsgIsPrintable( level ) != 0 );
}

/* take one message from the limit set by crgMsgSetMaxWarnMsgs(); the C library
   only applies the limit when it prints to stderr itself */
static PyObject* py_msg_consume_quota( PyObject* self, PyObject* unused ) {
    int remaining = crgPortGetMaxWarnMsgs();
    if ( remaining == 0 )
        Py_RETURN_FALSE;
    if ( remaining > 0 )
        crgMsgSetMaxWarnMsgs( remaining - 1 );
    Py_RETURN_TRUE;
}

static PyObject* py_msg_print( PyObject* self, PyObject* args ) {
    int level = 0;
    const char* text = NULL;
    if ( !PyArg_ParseTuple( args, "is:msg_print", &level, &text ) )
        return NULL;
    if ( text[0] != '\0' )
        crgMsgPrint( level, "%s", text );
    Py_RETURN_NONE;
}

/* invoke_callback(callback, level, text): call a user message callback; an
   exception is reported through sys.unraisablehook instead of propagating */
static PyObject* py_invoke_callback( PyObject* self, PyObject* args ) {
    PyObject* callback;
    int level;
    PyObject* text;
    PyObject* result;
    if ( !PyArg_ParseTuple( args, "OiU:invoke_callback", &callback, &level, &text ) )
        return NULL;
    result = PyObject_CallFunction( callback, "iO", level, text );
    if ( result == NULL )
        PyErr_WriteUnraisable( callback );
    else
        Py_DECREF( result );
    Py_RETURN_NONE;
}

static PyObject* py_msg_set_handler( PyObject* self, PyObject* handler ) {
    if ( !store_callback( handler, &g_msg_handler ) )
        return NULL;
    /* the bridge stays installed, so that the C library never writes to stderr;
       without a handler, messages are dropped */
    crgMsgSetCallback( c_msg_bridge );
    Py_RETURN_NONE;
}

static PyObject* py_calloc_set_callback( PyObject* self, PyObject* callback ) {
    if ( !store_callback( callback, &g_calloc_callback ) )
        return NULL;
    crgCallocSetCallback( g_calloc_callback != NULL ? c_calloc_bridge : NULL );
    Py_RETURN_NONE;
}

static PyObject* py_realloc_set_callback( PyObject* self, PyObject* callback ) {
    if ( !store_callback( callback, &g_realloc_callback ) )
        return NULL;
    crgReallocSetCallback( g_realloc_callback != NULL ? c_realloc_bridge : NULL );
    Py_RETURN_NONE;
}

static PyObject* py_free_set_callback( PyObject* self, PyObject* callback ) {
    if ( !store_callback( callback, &g_free_callback ) )
        return NULL;
    crgFreeSetCallback( g_free_callback != NULL ? c_free_bridge : NULL );
    Py_RETURN_NONE;
}

static PyObject* py_clear_allocator_callbacks( PyObject* self, PyObject* unused ) {
    crgCallocSetCallback( NULL );
    crgReallocSetCallback( NULL );
    crgFreeSetCallback( NULL );
    Py_CLEAR( g_calloc_callback );
    Py_CLEAR( g_realloc_callback );
    Py_CLEAR( g_free_callback );
    Py_RETURN_NONE;
}

static PyObject* py_calloc( PyObject* self, PyObject* args ) {
    unsigned long long nmemb = 0;
    unsigned long long size = 0;
    if ( !PyArg_ParseTuple( args, "KK:calloc", &nmemb, &size ) )
        return NULL;
    return PyLong_FromVoidPtr( crgCalloc( ( size_t ) nmemb, ( size_t ) size ) );
}

static PyObject* py_realloc( PyObject* self, PyObject* args ) {
    PyObject* ptr_obj = NULL;
    unsigned long long size = 0;
    void* ptr;
    if ( !PyArg_ParseTuple( args, "OK:realloc", &ptr_obj, &size ) )
        return NULL;
    ptr = PyLong_AsVoidPtr( ptr_obj );
    if ( PyErr_Occurred() )
        return NULL;
    return PyLong_FromVoidPtr( crgRealloc( ptr, ( size_t ) size ) );
}

static PyObject* py_free( PyObject* self, PyObject* arg ) {
    void* ptr = PyLong_AsVoidPtr( arg );
    if ( PyErr_Occurred() )
        return NULL;
    crgFree( ptr );
    Py_RETURN_NONE;
}

/* ------------------------------------------------------------------------- */
/* data sets                                                                 */
/* ------------------------------------------------------------------------- */

/* the path is converted with PyUnicode_FSConverter: native bytes on POSIX
   (including undecodable names), UTF-8 on Windows, which the patched loader
   opens with the wide-character file functions */
static PyObject* py_loader_read_file( PyObject* self, PyObject* args ) {
    PyObject* path = NULL;
    int data_set_id;
    if ( !PyArg_ParseTuple( args, "O&:loader_read_file", PyUnicode_FSConverter, &path ) )
        return NULL;
    data_set_id = crgLoaderReadFile( PyBytes_AS_STRING( path ) );
    Py_DECREF( path );
    return PyLong_FromLong( data_set_id > 0 ? data_set_id : 0 );
}

static PyObject* py_check( PyObject* self, PyObject* arg ) {
    int id;
    if ( !parse_int( arg, &id ) )
        return NULL;
    return py_bool( crgCheck( id ) );
}

static PyObject* py_dataset_release( PyObject* self, PyObject* arg ) {
    int id;
    if ( !parse_int( arg, &id ) )
        return NULL;
    return py_bool( crgDataSetRelease( id ) );
}

#define DATASET_VOID_FUNCTION( pyname, cfunc )                      \
    static PyObject* pyname( PyObject* self, PyObject* arg ) {      \
        int id;                                                     \
        if ( !parse_int( arg, &id ) )                               \
            return NULL;                                            \
        cfunc( id );                                                \
        Py_RETURN_NONE;                                             \
    }

DATASET_VOID_FUNCTION( py_dataset_print_header, crgDataPrintHeader )
DATASET_VOID_FUNCTION( py_dataset_print_channel_info, crgDataPrintChannelInfo )
DATASET_VOID_FUNCTION( py_dataset_print_road_info, crgDataPrintRoadInfo )
DATASET_VOID_FUNCTION( py_dataset_modifiers_print, crgDataSetModifiersPrint )
DATASET_VOID_FUNCTION( py_dataset_modifier_set_default, crgDataSetModifierSetDefault )
DATASET_VOID_FUNCTION( py_dataset_option_set_default, crgDataSetOptionSetDefault )
DATASET_VOID_FUNCTION( py_contact_point_delete_all, crgContactPointDeleteAll )

#define DATASET_RANGE_FUNCTION( pyname, cfunc, what )               \
    static PyObject* pyname( PyObject* self, PyObject* arg ) {      \
        int id;                                                     \
        double a = 0.0;                                             \
        double b = 0.0;                                             \
        if ( !parse_int( arg, &id ) )                               \
            return NULL;                                            \
        if ( !cfunc( id, &a, &b ) )                                 \
            return raise_error( "Failed to query the " what " of the data set" ); \
        return Py_BuildValue( "dd", a, b );                         \
    }

DATASET_RANGE_FUNCTION( py_dataset_get_u_range, crgDataSetGetURange, "u range" )
DATASET_RANGE_FUNCTION( py_dataset_get_v_range, crgDataSetGetVRange, "v range" )

/* whether long sections defined by position are equally spaced, by the rule
   of the loader (prepareFromPosDef) */
static int has_constant_v_spacing( const CrgDataStruct* crg_data ) {
    const double* v = crg_data->channelV.data;
    size_t i, n = crg_data->channelV.info.size;
    double dv, dv_min = 0.0, dv_max = 0.0;
    if ( v == NULL || n < 2 )
        return 0;
    for ( i = 1; i < n; i++ ) {
        dv = v[i] - v[i - 1];
        if ( i == 1 || dv < dv_min )
            dv_min = dv;
        if ( i == 1 || dv > dv_max )
            dv_max = dv;
    }
    return dv_min > 0.0 && ( dv_max - dv_min ) / dv_min < 1.e-3;
}

static PyObject* py_dataset_get_increments( PyObject* self, PyObject* arg ) {
    int id;
    double u_inc = 0.0;
    double v_inc = 0.0;
    const CrgDataStruct* crg_data;
    if ( !parse_int( arg, &id ) )
        return NULL;
    if ( !crgDataSetGetIncrements( id, &u_inc, &v_inc ) )
        return raise_error( "Failed to query the increments of the data set" );
    /* for long sections at variable positions, the loader keeps a fallback
       increment of 0.01 (or the header's value); report 0 instead */
    crg_data = crgDataSetAccess( id );
    if ( crg_data != NULL && ( crg_data->admin.defMask & dCrgDataDefVPos ) && !has_constant_v_spacing( crg_data ) )
        v_inc = 0.0;
    return Py_BuildValue( "dd", u_inc, v_inc );
}

static PyObject* py_dataset_get_closed_track( PyObject* self, PyObject* arg ) {
    int id;
    int is_closed = 0;
    double u_min = 0.0;
    double u_max = 0.0;
    int ok;
    if ( !parse_int( arg, &id ) )
        return NULL;
    ok = crgDataSetGetUtilityDataClosedTrack( id, &is_closed, &u_min, &u_max );
    /* the C library returns stale values instead of the documented NaN for
       reference lines which cannot be closed */
    if ( !ok || !is_closed ) {
        u_min = Py_NAN;
        u_max = Py_NAN;
    }
    return Py_BuildValue( "Nidd", py_bool( ok ), is_closed, u_min, u_max );
}

static PyObject* py_dataset_modifier_set_int( PyObject* self, PyObject* args ) {
    int id, option_id, value;
    if ( !PyArg_ParseTuple( args, "iii:dataset_modifier_set_int", &id, &option_id, &value ) )
        return NULL;
    return py_bool( crgDataSetModifierSetInt( id, ( unsigned int ) option_id, value ) );
}

static PyObject* py_dataset_modifier_set_double( PyObject* self, PyObject* args ) {
    int id, option_id;
    double value;
    if ( !PyArg_ParseTuple( args, "iid:dataset_modifier_set_double", &id, &option_id, &value ) )
        return NULL;
    return py_bool( crgDataSetModifierSetDouble( id, ( unsigned int ) option_id, value ) );
}

static PyObject* py_dataset_modifier_get_int( PyObject* self, PyObject* args ) {
    int id, option_id, value = 0, found;
    if ( !PyArg_ParseTuple( args, "ii:dataset_modifier_get_int", &id, &option_id ) )
        return NULL;
    found = crgDataSetModifierGetInt( id, ( unsigned int ) option_id, &value );
    return Py_BuildValue( "Ni", py_bool( found ), value );
}

static PyObject* py_dataset_modifier_get_double( PyObject* self, PyObject* args ) {
    int id, option_id, found;
    double value = 0.0;
    if ( !PyArg_ParseTuple( args, "ii:dataset_modifier_get_double", &id, &option_id ) )
        return NULL;
    found = crgDataSetModifierGetDouble( id, ( unsigned int ) option_id, &value );
    return Py_BuildValue( "Nd", py_bool( found ), value );
}

static PyObject* py_dataset_modifier_remove( PyObject* self, PyObject* args ) {
    int id, modifier_id;
    if ( !PyArg_ParseTuple( args, "ii:dataset_modifier_remove", &id, &modifier_id ) )
        return NULL;
    return py_bool( crgDataSetModifierRemove( id, ( unsigned int ) modifier_id ) );
}

static PyObject* py_dataset_modifier_remove_all( PyObject* self, PyObject* arg ) {
    int id;
    if ( !parse_int( arg, &id ) )
        return NULL;
    return py_bool( crgDataSetModifierRemoveAll( id ) );
}

/* Apply the modifiers like the OpenCRG demos do after crgCheck(): complete and
   validate them with crgCheckMods() first, apply them, then remove them so that
   they are applied only once (crgDataSetModifiersApply() documents this, but
   does not do it). Returns False if the modifiers are invalid. */
static PyObject* py_dataset_modifiers_apply( PyObject* self, PyObject* arg ) {
    int id;
    CrgDataStruct* crg_data;
    if ( !parse_int( arg, &id ) )
        return NULL;
    if ( !( crg_data = crgDataSetAccess( id ) ) )
        return raise_error( "Invalid data set id" );
    if ( !crgCheckMods( crg_data ) )
        Py_RETURN_FALSE;
    crgDataSetModifiersApply( id );
    crgDataSetModifierRemoveAll( id );
    Py_RETURN_TRUE;
}

/* ------------------------------------------------------------------------- */
/* grid access                                                               */
/* ------------------------------------------------------------------------- */

static PyObject* py_dataset_grid_shape( PyObject* self, PyObject* arg ) {
    int id;
    CrgDataStruct* crg_data;
    if ( !parse_int( arg, &id ) )
        return NULL;
    if ( !( crg_data = crgDataSetAccess( id ) ) )
        return raise_error( "Invalid data set id" );
    return Py_BuildValue( "nn", ( Py_ssize_t ) crg_data->channelU.info.size, ( Py_ssize_t ) crg_data->channelV.info.size );
}

/* accept "d" with native (or explicitly matching) byte order */
static int is_native_double_format( const char* format ) {
    const unsigned int one = 1;
    const int little_endian = *( const unsigned char* ) &one == 1;

    if ( format == NULL )
        return 0;
    if ( format[0] == '@' || format[0] == '=' || ( format[0] == '<' && little_endian ) ||
         ( ( format[0] == '>' || format[0] == '!' ) && !little_endian ) )
        format++;
    return strcmp( format, "d" ) == 0;
}

static int get_double_buffer( PyObject* obj, Py_buffer* view, int writable, Py_ssize_t* count ) {
    int flags = PyBUF_C_CONTIGUOUS | PyBUF_FORMAT | ( writable ? PyBUF_WRITABLE : 0 );
    if ( PyObject_GetBuffer( obj, view, flags ) < 0 )
        return 0;
    if ( view->itemsize != ( Py_ssize_t ) sizeof( double ) || !is_native_double_format( view->format ) ) {
        PyBuffer_Release( view );
        PyErr_SetString( PyExc_TypeError, "expected a C-contiguous buffer of native float64 values" );
        return 0;
    }
    *count = view->len / view->itemsize;
    return 1;
}

static void fill_channel( double* out, Py_ssize_t n, const CrgChannelStruct* channel, double fallback ) {
    Py_ssize_t i;
    if ( channel->data != NULL && ( Py_ssize_t ) channel->info.size == n ) {
        memcpy( out, channel->data, ( size_t ) n * sizeof( double ) );
    } else {
        for ( i = 0; i < n; i++ )
            out[i] = fallback;
    }
}

/* dataset_grid_fill(id, name, out): copy one array of the data set into a
   float64 buffer. name is "v" (nv values), "z" (nu x nv values, row-major by u)
   or one of "x", "y", "phi", "slope", "bank", "ref_z" (nu values). */
static PyObject* py_dataset_grid_fill( PyObject* self, PyObject* args ) {
    int id;
    const char* name;
    PyObject* out_obj;
    Py_buffer view;
    Py_ssize_t count, nu, nv, i, j;
    CrgDataStruct* crg_data;
    double* out;
    int ok = 1;

    if ( !PyArg_ParseTuple( args, "isO:dataset_grid_fill", &id, &name, &out_obj ) )
        return NULL;
    if ( !( crg_data = crgDataSetAccess( id ) ) )
        return raise_error( "Invalid data set id" );

    nu = ( Py_ssize_t ) crg_data->channelU.info.size;
    nv = ( Py_ssize_t ) crg_data->channelV.info.size;

    if ( !get_double_buffer( out_obj, &view, 1, &count ) )
        return NULL;
    out = ( double* ) view.buf;

    if ( strcmp( name, "z" ) == 0 ) {
        if ( count != nu * nv ) {
            ok = 0;
        } else {
            for ( j = 0; j < nv; j++ ) {
                const CrgChannelFStruct* channel = &( crg_data->channelZ[j] );
                for ( i = 0; i < nu; i++ )
                    out[i * nv + j] = ( double ) channel->data[i] + channel->info.mean;
            }
        }
    } else if ( strcmp( name, "v" ) == 0 ) {
        if ( count != nv )
            ok = 0;
        else
            memcpy( out, crg_data->channelV.data, ( size_t ) nv * sizeof( double ) );
    } else if ( count != nu ) {
        ok = 0;
    } else if ( strcmp( name, "x" ) == 0 ) {
        fill_channel( out, nu, &( crg_data->channelX ), Py_NAN );
    } else if ( strcmp( name, "y" ) == 0 ) {
        fill_channel( out, nu, &( crg_data->channelY ), Py_NAN );
    } else if ( strcmp( name, "phi" ) == 0 ) {
        fill_channel( out, nu, &( crg_data->channelPhi ), crg_data->channelPhi.info.first );
    } else if ( strcmp( name, "slope" ) == 0 ) {
        fill_channel( out, nu, &( crg_data->channelSlope ), crg_data->channelSlope.info.first );
    } else if ( strcmp( name, "bank" ) == 0 ) {
        fill_channel( out, nu, &( crg_data->channelBank ), crg_data->util.hasBank ? crg_data->channelBank.info.first : 0.0 );
    } else if ( strcmp( name, "ref_z" ) == 0 ) {
        if ( crg_data->channelRefZ.info.valid )
            fill_channel( out, nu, &( crg_data->channelRefZ ), crg_data->channelRefZ.info.first );
        else
            for ( i = 0; i < nu; i++ )
                out[i] = crg_data->channelRefZ.info.first;
    } else {
        PyBuffer_Release( &view );
        PyErr_Format( PyExc_ValueError, "unknown grid array '%s'", name );
        return NULL;
    }

    PyBuffer_Release( &view );
    if ( !ok ) {
        PyErr_SetString( PyExc_ValueError, "output buffer has the wrong size" );
        return NULL;
    }
    Py_RETURN_NONE;
}

/* ------------------------------------------------------------------------- */
/* contact points                                                            */
/* ------------------------------------------------------------------------- */

static PyObject* py_contact_point_create( PyObject* self, PyObject* arg ) {
    int id;
    if ( !parse_int( arg, &id ) )
        return NULL;
    return PyLong_FromLong( crgContactPointCreate( id ) );
}

static PyObject* py_contact_point_delete( PyObject* self, PyObject* arg ) {
    int cp_id;
    if ( !parse_int( arg, &cp_id ) )
        return NULL;
    return py_bool( crgContactPointDelete( cp_id ) );
}

static PyObject* py_cp_option_set_int( PyObject* self, PyObject* args ) {
    int cp_id, option_id, value;
    if ( !PyArg_ParseTuple( args, "iii:cp_option_set_int", &cp_id, &option_id, &value ) )
        return NULL;
    return py_bool( crgContactPointOptionSetInt( cp_id, ( unsigned int ) option_id, value ) );
}

static PyObject* py_cp_option_set_double( PyObject* self, PyObject* args ) {
    int cp_id, option_id;
    double value;
    if ( !PyArg_ParseTuple( args, "iid:cp_option_set_double", &cp_id, &option_id, &value ) )
        return NULL;
    return py_bool( crgContactPointOptionSetDouble( cp_id, ( unsigned int ) option_id, value ) );
}

static PyObject* py_cp_option_get_int( PyObject* self, PyObject* args ) {
    int cp_id, option_id, value = 0, found;
    if ( !PyArg_ParseTuple( args, "ii:cp_option_get_int", &cp_id, &option_id ) )
        return NULL;
    found = crgContactPointOptionGetInt( cp_id, ( unsigned int ) option_id, &value );
    return Py_BuildValue( "Ni", py_bool( found ), value );
}

static PyObject* py_cp_option_get_double( PyObject* self, PyObject* args ) {
    int cp_id, option_id, found;
    double value = 0.0;
    if ( !PyArg_ParseTuple( args, "ii:cp_option_get_double", &cp_id, &option_id ) )
        return NULL;
    found = crgContactPointOptionGetDouble( cp_id, ( unsigned int ) option_id, &value );
    return Py_BuildValue( "Nd", py_bool( found ), value );
}

static PyObject* py_cp_option_remove( PyObject* self, PyObject* args ) {
    int cp_id, option_id;
    if ( !PyArg_ParseTuple( args, "ii:cp_option_remove", &cp_id, &option_id ) )
        return NULL;
    return py_bool( crgContactPointOptionRemove( cp_id, ( unsigned int ) option_id ) );
}

static PyObject* py_cp_option_remove_all( PyObject* self, PyObject* arg ) {
    int cp_id;
    if ( !parse_int( arg, &cp_id ) )
        return NULL;
    return py_bool( crgContactPointOptionRemoveAll( cp_id ) );
}

static PyObject* py_cp_options_print( PyObject* self, PyObject* arg ) {
    int cp_id;
    if ( !parse_int( arg, &cp_id ) )
        return NULL;
    crgContactPointOptionsPrint( cp_id );
    Py_RETURN_NONE;
}

static PyObject* py_cp_set_default_options( PyObject* self, PyObject* arg ) {
    int cp_id;
    if ( !parse_int( arg, &cp_id ) )
        return NULL;
    crgContactPointSetDefaultOptions( cp_id );
    Py_RETURN_NONE;
}

static PyObject* py_cp_set_history( PyObject* self, PyObject* args ) {
    int cp_id, size;
    if ( !PyArg_ParseTuple( args, "ii:cp_set_history", &cp_id, &size ) )
        return NULL;
    return py_bool( crgContactPointSetHistory( cp_id, size ) );
}

/* ------------------------------------------------------------------------- */
/* evaluation                                                                */
/* ------------------------------------------------------------------------- */

#define OP_UV_TO_Z  0
#define OP_XY_TO_Z  1
#define OP_UV_TO_XY 2
#define OP_XY_TO_UV 3
#define OP_UV_TO_PK 4
#define OP_XY_TO_PK 5

/* Evaluate one point. Non-finite input is refused: the C library would convert
   it to an array index, which is undefined behaviour. */
static int evaluate( int op, int cp_id, double a, double b, double* r1, double* r2 ) {
    if ( !isfinite( a ) || !isfinite( b ) )
        return 0;
    switch ( op ) {
        case OP_UV_TO_Z:
            return crgEvaluv2z( cp_id, a, b, r1 );
        case OP_XY_TO_Z:
            return crgEvalxy2z( cp_id, a, b, r1 );
        case OP_UV_TO_XY:
            return crgEvaluv2xy( cp_id, a, b, r1, r2 );
        case OP_XY_TO_UV:
            return crgEvalxy2uv( cp_id, a, b, r1, r2 );
        case OP_UV_TO_PK:
            return crgEvaluv2pk( cp_id, a, b, r1, r2 );
        case OP_XY_TO_PK:
            return crgEvalxy2pk( cp_id, a, b, r1, r2 );
        default:
            return 0;
    }
}

static const char* const g_eval_failures[] = {
    "Failed to evaluate z at (u, v) = (%R, %R)",
    "Failed to evaluate z at (x, y) = (%R, %R)",
    "Failed to convert (u, v) = (%R, %R) to (x, y)",
    "Failed to convert (x, y) = (%R, %R) to (u, v)",
    "Failed to evaluate heading/curvature at (u, v) = (%R, %R)",
    "Failed to evaluate heading/curvature at (x, y) = (%R, %R)",
};

static PyObject* eval_failure( int op, PyObject* a, PyObject* b ) {
    PyObject* fa = PyFloat_FromDouble( PyFloat_AsDouble( a ) );
    PyObject* fb = PyFloat_FromDouble( PyFloat_AsDouble( b ) );
    if ( fa != NULL && fb != NULL )
        PyErr_Format( g_eval_error, g_eval_failures[op], fa, fb );
    Py_XDECREF( fa );
    Py_XDECREF( fb );
    return NULL;
}

#define EVAL_FUNCTION( pyname, op, nresults )                                               \
    static PyObject* pyname( PyObject* self, PyObject* const* args, Py_ssize_t nargs ) {   \
        int cp_id;                                                                          \
        double a, b, r1 = 0.0, r2 = 0.0;                                                    \
        if ( !parse_eval_args( args, nargs, &( #pyname )[3], &cp_id, &a, &b ) )                 \
            return NULL;                                                                    \
        if ( !evaluate( op, cp_id, a, b, &r1, &r2 ) )                                       \
            return eval_failure( op, args[1], args[2] );                                    \
        if ( nresults == 1 )                                                                \
            return PyFloat_FromDouble( r1 );                                                \
        return Py_BuildValue( "dd", r1, r2 );                                               \
    }

EVAL_FUNCTION( py_eval_uv_to_z, OP_UV_TO_Z, 1 )
EVAL_FUNCTION( py_eval_xy_to_z, OP_XY_TO_Z, 1 )
EVAL_FUNCTION( py_eval_uv_to_xy, OP_UV_TO_XY, 2 )
EVAL_FUNCTION( py_eval_xy_to_uv, OP_XY_TO_UV, 2 )
EVAL_FUNCTION( py_eval_uv_to_pk, OP_UV_TO_PK, 2 )
EVAL_FUNCTION( py_eval_xy_to_pk, OP_XY_TO_PK, 2 )

/* eval_many(op, cp_id, a, b, out1, out2): evaluate all points of the float64
   buffers a and b into out1 (and out2 for two results, otherwise None).
   Points which cannot be evaluated are set to NaN. Returns their number. */
static PyObject* py_eval_many( PyObject* self, PyObject* args ) {
    int op, cp_id;
    PyObject *a_obj, *b_obj, *out1_obj, *out2_obj;
    Py_buffer a_view, b_view, out1_view, out2_view;
    Py_ssize_t n, count, i, failures = 0;
    int two_results, ok = 1;
    const double *a, *b;
    double *out1, *out2 = NULL;

    if ( !PyArg_ParseTuple( args, "iiOOOO:eval_many", &op, &cp_id, &a_obj, &b_obj, &out1_obj, &out2_obj ) )
        return NULL;
    if ( op < OP_UV_TO_Z || op > OP_XY_TO_PK ) {
        PyErr_SetString( PyExc_ValueError, "unknown evaluation" );
        return NULL;
    }
    two_results = op >= OP_UV_TO_XY;
    if ( two_results == ( out2_obj == Py_None ) ) {
        PyErr_SetString( PyExc_ValueError, "wrong number of output buffers" );
        return NULL;
    }

    if ( !get_double_buffer( a_obj, &a_view, 0, &n ) )
        return NULL;
    if ( !get_double_buffer( b_obj, &b_view, 0, &count ) ) {
        PyBuffer_Release( &a_view );
        return NULL;
    }
    ok = count == n;
    if ( !get_double_buffer( out1_obj, &out1_view, 1, &count ) ) {
        PyBuffer_Release( &a_view );
        PyBuffer_Release( &b_view );
        return NULL;
    }
    ok = ok && count == n;
    if ( two_results ) {
        if ( !get_double_buffer( out2_obj, &out2_view, 1, &count ) ) {
            PyBuffer_Release( &a_view );
            PyBuffer_Release( &b_view );
            PyBuffer_Release( &out1_view );
            return NULL;
        }
        ok = ok && count == n;
        out2 = ( double* ) out2_view.buf;
    }

    if ( ok ) {
        a = ( const double* ) a_view.buf;
        b = ( const double* ) b_view.buf;
        out1 = ( double* ) out1_view.buf;
        for ( i = 0; i < n; i++ ) {
            double r1 = 0.0, r2 = 0.0;
            if ( evaluate( op, cp_id, a[i], b[i], &r1, &r2 ) ) {
                out1[i] = r1;
                if ( out2 != NULL )
                    out2[i] = r2;
            } else {
                out1[i] = Py_NAN;
                if ( out2 != NULL )
                    out2[i] = Py_NAN;
                failures++;
            }
        }
    }

    PyBuffer_Release( &a_view );
    PyBuffer_Release( &b_view );
    PyBuffer_Release( &out1_view );
    if ( two_results )
        PyBuffer_Release( &out2_view );

    if ( !ok ) {
        PyErr_SetString( PyExc_ValueError, "input and output buffers must have the same size" );
        return NULL;
    }
    return PyLong_FromSsize_t( failures );
}

/* ------------------------------------------------------------------------- */
/* module                                                                    */
/* ------------------------------------------------------------------------- */

static PyMethodDef module_methods[] = {
    {"get_release_info", py_get_release_info, METH_NOARGS, "Get the OpenCRG release info."},
    {"mem_release", py_mem_release, METH_NOARGS, "Release all memory held by OpenCRG."},
    {"msg_set_level", py_msg_set_level, METH_O, "Set the OpenCRG message level."},
    {"msg_get_level", py_msg_get_level, METH_NOARGS, "Get the OpenCRG message level."},
    {"msg_set_max_warn_msgs", py_msg_set_max_warn_msgs, METH_O, "Set the maximum number of messages."},
    {"msg_get_max_warn_msgs", py_msg_get_max_warn_msgs, METH_NOARGS, "Get the remaining number of messages."},
    {"msg_set_max_log_msgs", py_msg_set_max_log_msgs, METH_O, "Set the maximum number of log messages."},
    {"msg_is_printable", py_msg_is_printable, METH_O, "Check whether messages of a level are printable."},
    {"msg_consume_quota", py_msg_consume_quota, METH_NOARGS, "Take one message from the message limit."},
    {"msg_print", py_msg_print, METH_VARARGS, "Send a message through the OpenCRG message system."},
    {"msg_set_handler", py_msg_set_handler, METH_O, "Set the callable receiving OpenCRG messages."},
    {"invoke_callback", py_invoke_callback, METH_VARARGS, "Call a message callback, reporting exceptions as unraisable."},
    {"calloc_set_callback", py_calloc_set_callback, METH_O, "Set the calloc callback (callable or None)."},
    {"realloc_set_callback", py_realloc_set_callback, METH_O, "Set the realloc callback (callable or None)."},
    {"free_set_callback", py_free_set_callback, METH_O, "Set the free callback (callable or None)."},
    {"clear_allocator_callbacks", py_clear_allocator_callbacks, METH_NOARGS, "Clear the allocator callbacks."},
    {"calloc", py_calloc, METH_VARARGS, "Call OpenCRG calloc and return the pointer value."},
    {"realloc", py_realloc, METH_VARARGS, "Call OpenCRG realloc and return the pointer value."},
    {"free", py_free, METH_O, "Call OpenCRG free for a pointer value."},
    {"loader_read_file", py_loader_read_file, METH_VARARGS, "Load a CRG file; return the data set id or 0."},
    {"check", py_check, METH_O, "Check a data set for consistency."},
    {"dataset_release", py_dataset_release, METH_O, "Release a data set."},
    {"dataset_print_header", py_dataset_print_header, METH_O, "Print the data set header."},
    {"dataset_print_channel_info", py_dataset_print_channel_info, METH_O, "Print the data set channel info."},
    {"dataset_print_road_info", py_dataset_print_road_info, METH_O, "Print the data set road info."},
    {"dataset_get_u_range", py_dataset_get_u_range, METH_O, "Get the u range."},
    {"dataset_get_v_range", py_dataset_get_v_range, METH_O, "Get the v range."},
    {"dataset_get_increments", py_dataset_get_increments, METH_O, "Get the u/v increments."},
    {"dataset_get_closed_track", py_dataset_get_closed_track, METH_O, "Get the closed track utility data."},
    {"dataset_modifier_set_int", py_dataset_modifier_set_int, METH_VARARGS, "Set an integer modifier."},
    {"dataset_modifier_set_double", py_dataset_modifier_set_double, METH_VARARGS, "Set a double modifier."},
    {"dataset_modifier_get_int", py_dataset_modifier_get_int, METH_VARARGS, "Get an integer modifier."},
    {"dataset_modifier_get_double", py_dataset_modifier_get_double, METH_VARARGS, "Get a double modifier."},
    {"dataset_modifier_remove", py_dataset_modifier_remove, METH_VARARGS, "Remove a modifier."},
    {"dataset_modifier_remove_all", py_dataset_modifier_remove_all, METH_O, "Remove all modifiers."},
    {"dataset_modifiers_print", py_dataset_modifiers_print, METH_O, "Print the modifiers."},
    {"dataset_modifiers_apply", py_dataset_modifiers_apply, METH_O, "Check, apply and remove the modifiers."},
    {"dataset_modifier_set_default", py_dataset_modifier_set_default, METH_O, "Set the default modifiers."},
    {"dataset_option_set_default", py_dataset_option_set_default, METH_O, "Set the default data set options."},
    {"dataset_grid_shape", py_dataset_grid_shape, METH_O, "Get the number of cross and long sections."},
    {"dataset_grid_fill", py_dataset_grid_fill, METH_VARARGS, "Copy a grid array into a float64 buffer."},
    {"contact_point_create", py_contact_point_create, METH_O, "Create a contact point; return its id or -1."},
    {"contact_point_delete", py_contact_point_delete, METH_O, "Delete a contact point."},
    {"contact_point_delete_all", py_contact_point_delete_all, METH_O, "Delete all contact points of a data set."},
    {"cp_option_set_int", py_cp_option_set_int, METH_VARARGS, "Set an integer contact point option."},
    {"cp_option_set_double", py_cp_option_set_double, METH_VARARGS, "Set a double contact point option."},
    {"cp_option_get_int", py_cp_option_get_int, METH_VARARGS, "Get an integer contact point option."},
    {"cp_option_get_double", py_cp_option_get_double, METH_VARARGS, "Get a double contact point option."},
    {"cp_option_remove", py_cp_option_remove, METH_VARARGS, "Remove a contact point option."},
    {"cp_option_remove_all", py_cp_option_remove_all, METH_O, "Remove all contact point options."},
    {"cp_options_print", py_cp_options_print, METH_O, "Print the contact point options."},
    {"cp_set_default_options", py_cp_set_default_options, METH_O, "Set the default contact point options."},
    {"cp_set_history", py_cp_set_history, METH_VARARGS, "Set the contact point history size."},
    {"eval_uv_to_z", ( PyCFunction ) ( void ( * )( void ) ) py_eval_uv_to_z, METH_FASTCALL, "Evaluate z at (u, v)."},
    {"eval_xy_to_z", ( PyCFunction ) ( void ( * )( void ) ) py_eval_xy_to_z, METH_FASTCALL, "Evaluate z at (x, y)."},
    {"eval_uv_to_xy", ( PyCFunction ) ( void ( * )( void ) ) py_eval_uv_to_xy, METH_FASTCALL, "Convert (u, v) to (x, y)."},
    {"eval_xy_to_uv", ( PyCFunction ) ( void ( * )( void ) ) py_eval_xy_to_uv, METH_FASTCALL, "Convert (x, y) to (u, v)."},
    {"eval_uv_to_pk", ( PyCFunction ) ( void ( * )( void ) ) py_eval_uv_to_pk, METH_FASTCALL, "Evaluate heading/curvature at (u, v)."},
    {"eval_xy_to_pk", ( PyCFunction ) ( void ( * )( void ) ) py_eval_xy_to_pk, METH_FASTCALL, "Evaluate heading/curvature at (x, y)."},
    {"eval_many", py_eval_many, METH_VARARGS, "Evaluate many points from float64 buffers."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "Native bindings for the OpenCRG C API (private, see pycrg.api).",
    -1,
    module_methods
};

PyMODINIT_FUNC PyInit__native( void ) {
    PyObject* module;
    PyObject* errors = PyImport_ImportModule( "pycrg.errors" );

    if ( errors == NULL )
        return NULL;
    g_error = PyObject_GetAttrString( errors, "OpenCRGError" );
    g_eval_error = PyObject_GetAttrString( errors, "OpenCRGEvaluationError" );
    Py_DECREF( errors );
    if ( g_error == NULL || g_eval_error == NULL )
        return NULL;

    module = PyModule_Create( &module_def );
    if ( module == NULL )
        return NULL;

    if ( PyModule_AddIntConstant( module, "OP_UV_TO_Z", OP_UV_TO_Z ) < 0 ||
         PyModule_AddIntConstant( module, "OP_XY_TO_Z", OP_XY_TO_Z ) < 0 ||
         PyModule_AddIntConstant( module, "OP_UV_TO_XY", OP_UV_TO_XY ) < 0 ||
         PyModule_AddIntConstant( module, "OP_XY_TO_UV", OP_XY_TO_UV ) < 0 ||
         PyModule_AddIntConstant( module, "OP_UV_TO_PK", OP_UV_TO_PK ) < 0 ||
         PyModule_AddIntConstant( module, "OP_XY_TO_PK", OP_XY_TO_PK ) < 0 ) {
        Py_DECREF( module );
        return NULL;
    }
    return module;
}
