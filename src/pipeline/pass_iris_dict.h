#pragma once
#include "pipeline/pipeline.h"
#include "graph_buffer/graph_buffer.h"

typedef struct {
    cbm_gbuf_t *gbuf;
    const char *project_name;
    const char *iris_host;
    int         iris_port;
    const char *iris_namespace;
    const char *iris_user;
    const char *iris_pass;
    const char *iris_package_filter;
} cbm_iris_dict_cfg_t;

int pass_iris_dict_run(cbm_iris_dict_cfg_t *cfg);
