#pragma once

/**
 * E3V3SE OctoPrint plugin host layer (https://github.com/navaismo/Octoprint-LCD_E3V3SE).
 *
 * The flag is always compiled and stays false unless OCTOPRINT_PLUGIN is enabled
 * and a plugin-aware host announced itself (M115 or M9000 A1), so SD-card profiles
 * behave exactly as before.
 */

#include "../inc/MarlinConfig.h"

extern bool serial_connection_active;

#if ENABLED(OCTOPRINT_PLUGIN)
  extern char title[50];  // M9000 N: job title shown by the plugin (declared in dwin.h too)
#endif

// True when host prompts/actions should be sent: always for SD profiles, only after the host connected otherwise.
#define HOST_LINK_UP() TERN(OCTOPRINT_PLUGIN, serial_connection_active, true)
