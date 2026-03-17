#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "crgBaseLib.h"

static PyObject* g_msg_callback = NULL;
static PyObject* g_calloc_callback = NULL;
static PyObject* g_realloc_callback = NULL;
static PyObject* g_free_callback = NULL;

static int c_msg_callback_bridge(int level, char* message) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* result = NULL;
    int ret = 0;

    if (g_msg_callback == NULL) {
        PyGILState_Release(gil);
        return 0;
    }

    result = PyObject_CallFunction(g_msg_callback, "is", level, message != NULL ? message : "");
    if (result == NULL) {
        PyErr_Print();
        PyGILState_Release(gil);
        return 0;
    }

    ret = (int) PyLong_AsLong(result);
    if (PyErr_Occurred()) {
        PyErr_Clear();
        ret = 0;
    }

    Py_DECREF(result);
    PyGILState_Release(gil);
    return ret;
}

static void* c_calloc_callback_bridge(size_t nmemb, size_t size) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* result = NULL;
    void* ptr = NULL;

    if (g_calloc_callback == NULL) {
        PyGILState_Release(gil);
        return NULL;
    }

    result = PyObject_CallFunction(g_calloc_callback, "kk", (unsigned long long) nmemb, (unsigned long long) size);
    if (result == NULL) {
        PyErr_Print();
        PyGILState_Release(gil);
        return NULL;
    }

    if (result != Py_None) {
        ptr = PyLong_AsVoidPtr(result);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            ptr = NULL;
        }
    }

    Py_DECREF(result);
    PyGILState_Release(gil);
    return ptr;
}

static void* c_realloc_callback_bridge(void* ptr, size_t size) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* result = NULL;
    PyObject* ptr_obj = NULL;
    void* out_ptr = NULL;

    if (g_realloc_callback == NULL) {
        PyGILState_Release(gil);
        return NULL;
    }

    ptr_obj = PyLong_FromVoidPtr(ptr);
    if (ptr_obj == NULL) {
        PyGILState_Release(gil);
        return NULL;
    }

    result = PyObject_CallFunction(g_realloc_callback, "Ok", ptr_obj, (unsigned long long) size);
    Py_DECREF(ptr_obj);
    if (result == NULL) {
        PyErr_Print();
        PyGILState_Release(gil);
        return NULL;
    }

    if (result != Py_None) {
        out_ptr = PyLong_AsVoidPtr(result);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            out_ptr = NULL;
        }
    }

    Py_DECREF(result);
    PyGILState_Release(gil);
    return out_ptr;
}

static void c_free_callback_bridge(void* ptr) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* result = NULL;
    PyObject* ptr_obj = NULL;

    if (g_free_callback == NULL) {
        PyGILState_Release(gil);
        return;
    }

    ptr_obj = PyLong_FromVoidPtr(ptr);
    if (ptr_obj == NULL) {
        PyGILState_Release(gil);
        return;
    }

    result = PyObject_CallFunction(g_free_callback, "O", ptr_obj);
    Py_DECREF(ptr_obj);
    if (result == NULL) {
        PyErr_Print();
        PyGILState_Release(gil);
        return;
    }

    Py_DECREF(result);
    PyGILState_Release(gil);
}

static int install_python_callback(PyObject* callback, PyObject** slot) {
    if (callback != Py_None && !PyCallable_Check(callback)) {
        PyErr_SetString(PyExc_TypeError, "callback must be callable or None");
        return 0;
    }

    Py_XINCREF(callback == Py_None ? NULL : callback);
    Py_XDECREF(*slot);
    *slot = callback == Py_None ? NULL : callback;
    return 1;
}

static PyObject* py_bool(int ok) {
    return PyBool_FromLong(ok ? 1 : 0);
}

static PyObject* py_get_release_info(PyObject* self, PyObject* args) {
    (void) self;
    (void) args;
    return PyUnicode_FromString(crgGetReleaseInfo());
}

static PyObject* py_mem_release(PyObject* self, PyObject* args) {
    (void) self;
    (void) args;
    crgMemRelease();
    Py_RETURN_NONE;
}

static PyObject* py_msg_set_level(PyObject* self, PyObject* args) {
    int level = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &level)) {
        return NULL;
    }
    crgMsgSetLevel(level);
    Py_RETURN_NONE;
}

static PyObject* py_msg_set_max_warn_msgs(PyObject* self, PyObject* args) {
    int max_no = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &max_no)) {
        return NULL;
    }
    crgMsgSetMaxWarnMsgs(max_no);
    Py_RETURN_NONE;
}

static PyObject* py_msg_set_max_log_msgs(PyObject* self, PyObject* args) {
    int max_no = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &max_no)) {
        return NULL;
    }
    crgMsgSetMaxLogMsgs(max_no);
    Py_RETURN_NONE;
}

static PyObject* py_msg_is_printable(PyObject* self, PyObject* args) {
    int level = 0;
    int ret = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &level)) {
        return NULL;
    }
    ret = crgMsgIsPrintable(level);
    return py_bool(ret == 0);
}

static PyObject* py_msg_print(PyObject* self, PyObject* args) {
    int level = 0;
    const char* text = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "is", &level, &text)) {
        return NULL;
    }
    crgMsgPrint(level, "%s", text);
    Py_RETURN_NONE;
}

static PyObject* py_msg_set_callback(PyObject* self, PyObject* args) {
    PyObject* callback = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "O", &callback)) {
        return NULL;
    }
    if (!install_python_callback(callback, &g_msg_callback)) {
        return NULL;
    }
    crgMsgSetCallback(g_msg_callback != NULL ? c_msg_callback_bridge : NULL);
    Py_RETURN_NONE;
}

static PyObject* py_calloc_set_callback(PyObject* self, PyObject* args) {
    PyObject* callback = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "O", &callback)) {
        return NULL;
    }
    if (!install_python_callback(callback, &g_calloc_callback)) {
        return NULL;
    }
    crgCallocSetCallback(g_calloc_callback != NULL ? c_calloc_callback_bridge : NULL);
    Py_RETURN_NONE;
}

static PyObject* py_realloc_set_callback(PyObject* self, PyObject* args) {
    PyObject* callback = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "O", &callback)) {
        return NULL;
    }
    if (!install_python_callback(callback, &g_realloc_callback)) {
        return NULL;
    }
    crgReallocSetCallback(g_realloc_callback != NULL ? c_realloc_callback_bridge : NULL);
    Py_RETURN_NONE;
}

static PyObject* py_free_set_callback(PyObject* self, PyObject* args) {
    PyObject* callback = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "O", &callback)) {
        return NULL;
    }
    if (!install_python_callback(callback, &g_free_callback)) {
        return NULL;
    }
    crgFreeSetCallback(g_free_callback != NULL ? c_free_callback_bridge : NULL);
    Py_RETURN_NONE;
}

static PyObject* py_clear_callbacks(PyObject* self, PyObject* args) {
    (void) self;
    (void) args;
    crgMsgSetCallback(NULL);
    crgCallocSetCallback(NULL);
    crgReallocSetCallback(NULL);
    crgFreeSetCallback(NULL);
    Py_XDECREF(g_msg_callback);
    Py_XDECREF(g_calloc_callback);
    Py_XDECREF(g_realloc_callback);
    Py_XDECREF(g_free_callback);
    g_msg_callback = NULL;
    g_calloc_callback = NULL;
    g_realloc_callback = NULL;
    g_free_callback = NULL;
    Py_RETURN_NONE;
}

static PyObject* py_calloc(PyObject* self, PyObject* args) {
    unsigned long long nmemb = 0;
    unsigned long long size = 0;
    void* ptr = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "KK", &nmemb, &size)) {
        return NULL;
    }
    ptr = crgCalloc((size_t) nmemb, (size_t) size);
    return PyLong_FromVoidPtr(ptr);
}

static PyObject* py_realloc(PyObject* self, PyObject* args) {
    PyObject* ptr_obj = NULL;
    unsigned long long size = 0;
    void* ptr = NULL;
    void* out_ptr = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "OK", &ptr_obj, &size)) {
        return NULL;
    }
    ptr = PyLong_AsVoidPtr(ptr_obj);
    if (PyErr_Occurred()) {
        return NULL;
    }
    out_ptr = crgRealloc(ptr, (size_t) size);
    return PyLong_FromVoidPtr(out_ptr);
}

static PyObject* py_free(PyObject* self, PyObject* args) {
    PyObject* ptr_obj = NULL;
    void* ptr = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "O", &ptr_obj)) {
        return NULL;
    }
    ptr = PyLong_AsVoidPtr(ptr_obj);
    if (PyErr_Occurred()) {
        return NULL;
    }
    crgFree(ptr);
    Py_RETURN_NONE;
}

static PyObject* py_loader_read_file(PyObject* self, PyObject* args) {
    const char* path = NULL;
    (void) self;
    if (!PyArg_ParseTuple(args, "s", &path)) {
        return NULL;
    }
    return PyLong_FromLong(crgLoaderReadFile(path));
}

static PyObject* py_check(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    return py_bool(crgCheck(data_set_id));
}

static PyObject* py_dataset_release(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    return py_bool(crgDataSetRelease(data_set_id));
}

static PyObject* py_dataset_print_header(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgDataPrintHeader(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_dataset_print_channel_info(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgDataPrintChannelInfo(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_dataset_print_road_info(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgDataPrintRoadInfo(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_dataset_get_u_range(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    double u_min = 0.0;
    double u_max = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    if (!crgDataSetGetURange(data_set_id, &u_min, &u_max)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to query dataset u range");
        return NULL;
    }
    return Py_BuildValue("dd", u_min, u_max);
}

static PyObject* py_dataset_get_v_range(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    double v_min = 0.0;
    double v_max = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    if (!crgDataSetGetVRange(data_set_id, &v_min, &v_max)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to query dataset v range");
        return NULL;
    }
    return Py_BuildValue("dd", v_min, v_max);
}

static PyObject* py_dataset_get_increments(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    double u_inc = 0.0;
    double v_inc = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    if (!crgDataSetGetIncrements(data_set_id, &u_inc, &v_inc)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to query dataset increments");
        return NULL;
    }
    return Py_BuildValue("dd", u_inc, v_inc);
}

static PyObject* py_dataset_get_closed_track(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    int is_closed = 0;
    double u_close_min = 0.0;
    double u_close_max = 0.0;
    int ok = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    ok = crgDataSetGetUtilityDataClosedTrack(data_set_id, &is_closed, &u_close_min, &u_close_max);
    return Py_BuildValue("Nidd", py_bool(ok), is_closed, u_close_min, u_close_max);
}

static PyObject* py_dataset_modifier_set_int(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    int option_id = 0;
    int option_value = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "iii", &data_set_id, &option_id, &option_value)) {
        return NULL;
    }
    return py_bool(crgDataSetModifierSetInt(data_set_id, (unsigned int) option_id, option_value));
}

static PyObject* py_dataset_modifier_set_double(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    int option_id = 0;
    double option_value = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "iid", &data_set_id, &option_id, &option_value)) {
        return NULL;
    }
    return py_bool(crgDataSetModifierSetDouble(data_set_id, (unsigned int) option_id, option_value));
}

static PyObject* py_dataset_modifier_get_int(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    int option_id = 0;
    int option_value = 0;
    int found = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &data_set_id, &option_id)) {
        return NULL;
    }
    found = crgDataSetModifierGetInt(data_set_id, (unsigned int) option_id, &option_value);
    return Py_BuildValue("Ni", py_bool(found), option_value);
}

static PyObject* py_dataset_modifier_get_double(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    int option_id = 0;
    double option_value = 0.0;
    int found = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &data_set_id, &option_id)) {
        return NULL;
    }
    found = crgDataSetModifierGetDouble(data_set_id, (unsigned int) option_id, &option_value);
    return Py_BuildValue("Nd", py_bool(found), option_value);
}

static PyObject* py_dataset_modifier_remove(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    int mod_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &data_set_id, &mod_id)) {
        return NULL;
    }
    return py_bool(crgDataSetModifierRemove(data_set_id, (unsigned int) mod_id));
}

static PyObject* py_dataset_modifier_remove_all(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    return py_bool(crgDataSetModifierRemoveAll(data_set_id));
}

static PyObject* py_dataset_modifiers_print(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgDataSetModifiersPrint(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_dataset_modifiers_apply(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgDataSetModifiersApply(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_dataset_modifier_set_default(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgDataSetModifierSetDefault(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_dataset_option_set_default(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgDataSetOptionSetDefault(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_contact_point_create(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    return PyLong_FromLong(crgContactPointCreate(data_set_id));
}

static PyObject* py_contact_point_delete(PyObject* self, PyObject* args) {
    int cp_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &cp_id)) {
        return NULL;
    }
    return py_bool(crgContactPointDelete(cp_id));
}

static PyObject* py_contact_point_delete_all(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &data_set_id)) {
        return NULL;
    }
    crgContactPointDeleteAll(data_set_id);
    Py_RETURN_NONE;
}

static PyObject* py_cp_option_set_int(PyObject* self, PyObject* args) {
    int cp_id = 0;
    int option_id = 0;
    int option_value = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "iii", &cp_id, &option_id, &option_value)) {
        return NULL;
    }
    return py_bool(crgContactPointOptionSetInt(cp_id, (unsigned int) option_id, option_value));
}

static PyObject* py_cp_option_set_double(PyObject* self, PyObject* args) {
    int cp_id = 0;
    int option_id = 0;
    double option_value = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "iid", &cp_id, &option_id, &option_value)) {
        return NULL;
    }
    return py_bool(crgContactPointOptionSetDouble(cp_id, (unsigned int) option_id, option_value));
}

static PyObject* py_cp_option_get_int(PyObject* self, PyObject* args) {
    int cp_id = 0;
    int option_id = 0;
    int option_value = 0;
    int found = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &cp_id, &option_id)) {
        return NULL;
    }
    found = crgContactPointOptionGetInt(cp_id, (unsigned int) option_id, &option_value);
    return Py_BuildValue("Ni", py_bool(found), option_value);
}

static PyObject* py_cp_option_get_double(PyObject* self, PyObject* args) {
    int cp_id = 0;
    int option_id = 0;
    double option_value = 0.0;
    int found = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &cp_id, &option_id)) {
        return NULL;
    }
    found = crgContactPointOptionGetDouble(cp_id, (unsigned int) option_id, &option_value);
    return Py_BuildValue("Nd", py_bool(found), option_value);
}

static PyObject* py_cp_option_remove(PyObject* self, PyObject* args) {
    int cp_id = 0;
    int option_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &cp_id, &option_id)) {
        return NULL;
    }
    return py_bool(crgContactPointOptionRemove(cp_id, (unsigned int) option_id));
}

static PyObject* py_cp_option_remove_all(PyObject* self, PyObject* args) {
    int cp_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &cp_id)) {
        return NULL;
    }
    return py_bool(crgContactPointOptionRemoveAll(cp_id));
}

static PyObject* py_cp_options_print(PyObject* self, PyObject* args) {
    int cp_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &cp_id)) {
        return NULL;
    }
    crgContactPointOptionsPrint(cp_id);
    Py_RETURN_NONE;
}

static PyObject* py_cp_set_default_options(PyObject* self, PyObject* args) {
    int cp_id = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "i", &cp_id)) {
        return NULL;
    }
    crgContactPointSetDefaultOptions(cp_id);
    Py_RETURN_NONE;
}

static PyObject* py_cp_set_history(PyObject* self, PyObject* args) {
    int cp_id = 0;
    int hist_size = 0;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &cp_id, &hist_size)) {
        return NULL;
    }
    return py_bool(crgContactPointSetHistory(cp_id, hist_size));
}

static PyObject* py_eval_xy_to_uv(PyObject* self, PyObject* args) {
    int cp_id = 0;
    double x = 0.0;
    double y = 0.0;
    double u = 0.0;
    double v = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "idd", &cp_id, &x, &y)) {
        return NULL;
    }
    if (!crgEvalxy2uv(cp_id, x, y, &u, &v)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to convert (x, y) to (u, v)");
        return NULL;
    }
    return Py_BuildValue("dd", u, v);
}

static PyObject* py_eval_uv_to_xy(PyObject* self, PyObject* args) {
    int cp_id = 0;
    double u = 0.0;
    double v = 0.0;
    double x = 0.0;
    double y = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "idd", &cp_id, &u, &v)) {
        return NULL;
    }
    if (!crgEvaluv2xy(cp_id, u, v, &x, &y)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to convert (u, v) to (x, y)");
        return NULL;
    }
    return Py_BuildValue("dd", x, y);
}

static PyObject* py_eval_uv_to_z(PyObject* self, PyObject* args) {
    int cp_id = 0;
    double u = 0.0;
    double v = 0.0;
    double z = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "idd", &cp_id, &u, &v)) {
        return NULL;
    }
    if (!crgEvaluv2z(cp_id, u, v, &z)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to evaluate z at (u, v)");
        return NULL;
    }
    return PyFloat_FromDouble(z);
}

static PyObject* py_eval_xy_to_z(PyObject* self, PyObject* args) {
    int cp_id = 0;
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "idd", &cp_id, &x, &y)) {
        return NULL;
    }
    if (!crgEvalxy2z(cp_id, x, y, &z)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to evaluate z at (x, y)");
        return NULL;
    }
    return PyFloat_FromDouble(z);
}

static PyObject* py_eval_uv_to_pk(PyObject* self, PyObject* args) {
    int cp_id = 0;
    double u = 0.0;
    double v = 0.0;
    double phi = 0.0;
    double curv = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "idd", &cp_id, &u, &v)) {
        return NULL;
    }
    if (!crgEvaluv2pk(cp_id, u, v, &phi, &curv)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to evaluate heading/curvature at (u, v)");
        return NULL;
    }
    return Py_BuildValue("dd", phi, curv);
}

static PyObject* py_eval_xy_to_pk(PyObject* self, PyObject* args) {
    int cp_id = 0;
    double x = 0.0;
    double y = 0.0;
    double phi = 0.0;
    double curv = 0.0;
    (void) self;
    if (!PyArg_ParseTuple(args, "idd", &cp_id, &x, &y)) {
        return NULL;
    }
    if (!crgEvalxy2pk(cp_id, x, y, &phi, &curv)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to evaluate heading/curvature at (x, y)");
        return NULL;
    }
    return Py_BuildValue("dd", phi, curv);
}

static PyObject* py_open_file(PyObject* self, PyObject* args) {
    const char* path = NULL;
    int data_set_id = 0;
    int cp_id = -1;
    (void) self;
    if (!PyArg_ParseTuple(args, "s", &path)) {
        return NULL;
    }
    data_set_id = crgLoaderReadFile(path);
    if (data_set_id <= 0) {
        PyErr_SetString(PyExc_RuntimeError, "OpenCRG failed to load file");
        return NULL;
    }
    cp_id = crgContactPointCreate(data_set_id);
    if (cp_id < 0) {
        crgDataSetRelease(data_set_id);
        PyErr_SetString(PyExc_RuntimeError, "OpenCRG failed to create contact point");
        return NULL;
    }
    return Py_BuildValue("ii", data_set_id, cp_id);
}

static PyObject* py_close(PyObject* self, PyObject* args) {
    int data_set_id = 0;
    int cp_id = -1;
    (void) self;
    if (!PyArg_ParseTuple(args, "ii", &data_set_id, &cp_id)) {
        return NULL;
    }
    if (cp_id >= 0) {
        crgContactPointDelete(cp_id);
    }
    if (data_set_id > 0) {
        crgDataSetRelease(data_set_id);
    }
    Py_RETURN_NONE;
}

static PyObject* py_u_range(PyObject* self, PyObject* args) {
    return py_dataset_get_u_range(self, args);
}

static PyObject* py_v_range(PyObject* self, PyObject* args) {
    return py_dataset_get_v_range(self, args);
}

static PyObject* py_uv_to_z(PyObject* self, PyObject* args) {
    return py_eval_uv_to_z(self, args);
}

static PyObject* py_xy_to_z(PyObject* self, PyObject* args) {
    return py_eval_xy_to_z(self, args);
}

static PyObject* py_uv_to_xy(PyObject* self, PyObject* args) {
    return py_eval_uv_to_xy(self, args);
}

static PyObject* py_xy_to_uv(PyObject* self, PyObject* args) {
    return py_eval_xy_to_uv(self, args);
}

static PyMethodDef module_methods[] = {
    {"get_release_info", py_get_release_info, METH_NOARGS, "Get OpenCRG release info."},
    {"mem_release", py_mem_release, METH_NOARGS, "Release all memory held by OpenCRG."},
    {"msg_set_level", py_msg_set_level, METH_VARARGS, "Set OpenCRG message level."},
    {"msg_set_max_warn_msgs", py_msg_set_max_warn_msgs, METH_VARARGS, "Set max warning/debug message count."},
    {"msg_set_max_log_msgs", py_msg_set_max_log_msgs, METH_VARARGS, "Set max log message count."},
    {"msg_is_printable", py_msg_is_printable, METH_VARARGS, "Check if a message level is printable."},
    {"msg_print", py_msg_print, METH_VARARGS, "Print a message through OpenCRG message system."},
    {"msg_set_callback", py_msg_set_callback, METH_VARARGS, "Set message callback (callable or None)."},
    {"calloc_set_callback", py_calloc_set_callback, METH_VARARGS, "Set calloc callback (callable or None)."},
    {"realloc_set_callback", py_realloc_set_callback, METH_VARARGS, "Set realloc callback (callable or None)."},
    {"free_set_callback", py_free_set_callback, METH_VARARGS, "Set free callback (callable or None)."},
    {"clear_callbacks", py_clear_callbacks, METH_NOARGS, "Clear all registered callbacks."},
    {"calloc", py_calloc, METH_VARARGS, "Call OpenCRG calloc and return pointer value."},
    {"realloc", py_realloc, METH_VARARGS, "Call OpenCRG realloc and return pointer value."},
    {"free", py_free, METH_VARARGS, "Call OpenCRG free for pointer value."},
    {"loader_read_file", py_loader_read_file, METH_VARARGS, "Load CRG file and return dataset id."},
    {"check", py_check, METH_VARARGS, "Validate dataset consistency."},
    {"dataset_release", py_dataset_release, METH_VARARGS, "Release dataset by id."},
    {"dataset_print_header", py_dataset_print_header, METH_VARARGS, "Print dataset header."},
    {"dataset_print_channel_info", py_dataset_print_channel_info, METH_VARARGS, "Print dataset channel info."},
    {"dataset_print_road_info", py_dataset_print_road_info, METH_VARARGS, "Print dataset road info."},
    {"dataset_get_u_range", py_dataset_get_u_range, METH_VARARGS, "Get dataset u range."},
    {"dataset_get_v_range", py_dataset_get_v_range, METH_VARARGS, "Get dataset v range."},
    {"dataset_get_increments", py_dataset_get_increments, METH_VARARGS, "Get dataset u/v increments."},
    {"dataset_get_closed_track", py_dataset_get_closed_track, METH_VARARGS, "Get closed track utility data."},
    {"dataset_modifier_set_int", py_dataset_modifier_set_int, METH_VARARGS, "Set integer dataset modifier."},
    {"dataset_modifier_set_double", py_dataset_modifier_set_double, METH_VARARGS, "Set double dataset modifier."},
    {"dataset_modifier_get_int", py_dataset_modifier_get_int, METH_VARARGS, "Get integer dataset modifier."},
    {"dataset_modifier_get_double", py_dataset_modifier_get_double, METH_VARARGS, "Get double dataset modifier."},
    {"dataset_modifier_remove", py_dataset_modifier_remove, METH_VARARGS, "Remove dataset modifier."},
    {"dataset_modifier_remove_all", py_dataset_modifier_remove_all, METH_VARARGS, "Remove all dataset modifiers."},
    {"dataset_modifiers_print", py_dataset_modifiers_print, METH_VARARGS, "Print dataset modifiers."},
    {"dataset_modifiers_apply", py_dataset_modifiers_apply, METH_VARARGS, "Apply and clear dataset modifiers."},
    {"dataset_modifier_set_default", py_dataset_modifier_set_default, METH_VARARGS, "Set default dataset modifiers."},
    {"dataset_option_set_default", py_dataset_option_set_default, METH_VARARGS, "Set default dataset options."},
    {"contact_point_create", py_contact_point_create, METH_VARARGS, "Create contact point for dataset."},
    {"contact_point_delete", py_contact_point_delete, METH_VARARGS, "Delete contact point by id."},
    {"contact_point_delete_all", py_contact_point_delete_all, METH_VARARGS, "Delete all contact points for dataset."},
    {"cp_option_set_int", py_cp_option_set_int, METH_VARARGS, "Set integer contact point option."},
    {"cp_option_set_double", py_cp_option_set_double, METH_VARARGS, "Set double contact point option."},
    {"cp_option_get_int", py_cp_option_get_int, METH_VARARGS, "Get integer contact point option."},
    {"cp_option_get_double", py_cp_option_get_double, METH_VARARGS, "Get double contact point option."},
    {"cp_option_remove", py_cp_option_remove, METH_VARARGS, "Remove contact point option."},
    {"cp_option_remove_all", py_cp_option_remove_all, METH_VARARGS, "Remove all contact point options."},
    {"cp_options_print", py_cp_options_print, METH_VARARGS, "Print contact point options."},
    {"cp_set_default_options", py_cp_set_default_options, METH_VARARGS, "Set default contact point options."},
    {"cp_set_history", py_cp_set_history, METH_VARARGS, "Set contact point history size."},
    {"eval_xy_to_uv", py_eval_xy_to_uv, METH_VARARGS, "Convert (x, y) to (u, v)."},
    {"eval_uv_to_xy", py_eval_uv_to_xy, METH_VARARGS, "Convert (u, v) to (x, y)."},
    {"eval_uv_to_z", py_eval_uv_to_z, METH_VARARGS, "Evaluate z at (u, v)."},
    {"eval_xy_to_z", py_eval_xy_to_z, METH_VARARGS, "Evaluate z at (x, y)."},
    {"eval_uv_to_pk", py_eval_uv_to_pk, METH_VARARGS, "Evaluate heading/curvature at (u, v)."},
    {"eval_xy_to_pk", py_eval_xy_to_pk, METH_VARARGS, "Evaluate heading/curvature at (x, y)."},
    {"open_file", py_open_file, METH_VARARGS, "Compatibility helper: open file and create contact point."},
    {"close", py_close, METH_VARARGS, "Compatibility helper: release contact point and dataset."},
    {"u_range", py_u_range, METH_VARARGS, "Compatibility helper: get u range."},
    {"v_range", py_v_range, METH_VARARGS, "Compatibility helper: get v range."},
    {"uv_to_z", py_uv_to_z, METH_VARARGS, "Compatibility helper: evaluate z for (u, v)."},
    {"xy_to_z", py_xy_to_z, METH_VARARGS, "Compatibility helper: evaluate z for (x, y)."},
    {"uv_to_xy", py_uv_to_xy, METH_VARARGS, "Compatibility helper: convert (u, v) to (x, y)."},
    {"xy_to_uv", py_xy_to_uv, METH_VARARGS, "Compatibility helper: convert (x, y) to (u, v)."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "Native OpenCRG bindings",
    -1,
    module_methods
};

PyMODINIT_FUNC PyInit__native(void) {
    return PyModule_Create(&module_def);
}
