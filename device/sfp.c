/*
 * Tunable SFP UART/JSON command service.
 *
 * Copy this file into the Vitis application in place of the old demo main
 * when Python needs to control the SFP through a serial port. The original
 * E:\vivado\vitis_2\app_component\sfp.c is intentionally left unchanged.
 *
 * Use order:
 *   1. Add this file to the Vitis application that uses
 *      E:\vivado\sfp_project_1 and build the application.
 *   2. Download/run the built ELF on the FPGA/SoC board first. This program
 *      must already be running because it owns AXI GPIO and AXI IIC.
 *   3. Start the Python controller on the PC, for example:
 *        with device.SFP(transport="serial", serial_port="COM3") as sfp:
 *            sfp.set_channel(10)
 *
 * The Python code is only the upper controller. It does not directly access
 * the SFP I2C bus; all low-level GPIO/IIC work stays in this firmware.
 *
 * Protocol: one ASCII command per line, one JSON object per response line.
 *
 *   INFO
 *   GET_CH
 *   SET_CH <1..96>
 *   GET_STATUS
 *   GET_DDM
 *   TX ON
 *   TX OFF
 *   HELP
 */

#include "xparameters.h"
#include "xgpio.h"
#include "xiic.h"
#include "xil_printf.h"
#include "sleep.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define GPIO_DEVICE_ID   XPAR_XGPIO_0_BASEADDR
#define IIC_DEVICE_ID    XPAR_XIIC_0_BASEADDR

#define GPIO_CHANNEL     1
#define TX_DISABLE_MASK  0x01U

#define SFP_A0_ADDR      0x50U
#define SFP_A2_ADDR      0x51U

#define SFP_A2_PAGE_SELECT      127U
#define SFP_8690_PAGE_TUNE      0x02U

#define SFP_8690_CAPABILITY     128U
#define SFP_8690_CHANNEL_MSB    144U
#define SFP_8690_STATUS         168U
#define SFP_8690_LATCH_STATUS   172U

#define CMD_MAX_LEN             64

static XGpio Gpio;
static XIic Iic;

static char g_vendor[17];
static char g_part_number[17];
static char g_serial_number[17];
static uint8_t g_capability;
static int g_hw_ready;

static uint16_t be16_to_u16(const uint8_t *p)
{
    return ((uint16_t)p[0] << 8) | (uint16_t)p[1];
}

static int16_t be16_to_s16(const uint8_t *p)
{
    return (int16_t)(((uint16_t)p[0] << 8) | (uint16_t)p[1]);
}

static void copy_ascii_trim_json_safe(char *dst, const uint8_t *src, int len)
{
    int i;

    for (i = 0; i < len; ++i) {
        char c = (char)src[i];
        if (c < 0x20 || c == '"' || c == '\\') {
            c = ' ';
        }
        dst[i] = c;
    }
    dst[len] = '\0';

    for (i = len - 1; i >= 0; --i) {
        if (dst[i] == ' ' || dst[i] == '\0') {
            dst[i] = '\0';
        } else {
            break;
        }
    }
}

static int starts_with(const char *s, const char *prefix)
{
    return strncmp(s, prefix, strlen(prefix)) == 0;
}

static int sfp_gpio_init(void)
{
    int status = XGpio_Initialize(&Gpio, GPIO_DEVICE_ID);
    if (status != XST_SUCCESS) {
        return status;
    }

    XGpio_SetDataDirection(&Gpio, GPIO_CHANNEL, 0x0U);
    XGpio_DiscreteWrite(&Gpio, GPIO_CHANNEL, TX_DISABLE_MASK);
    return XST_SUCCESS;
}

static void sfp_set_tx_disable(int disable)
{
    XGpio_DiscreteWrite(&Gpio, GPIO_CHANNEL, disable ? TX_DISABLE_MASK : 0x0U);
}

static int sfp_iic_init(void)
{
    int status = XIic_Initialize(&Iic, IIC_DEVICE_ID);
    if (status != XST_SUCCESS) {
        return status;
    }

    status = XIic_Start(&Iic);
    if (status != XST_SUCCESS) {
        return status;
    }

    XIic_IntrGlobalDisable(Iic.BaseAddress);
    return XST_SUCCESS;
}

static int sfp_i2c_random_read(uint8_t dev_addr, uint8_t offset, uint8_t *buf, int len)
{
    uint8_t off = offset;
    int sent = XIic_Send(Iic.BaseAddress, dev_addr, &off, 1, XIIC_REPEATED_START);
    if (sent != 1) {
        return XST_FAILURE;
    }

    int recv = XIic_Recv(Iic.BaseAddress, dev_addr, buf, len, XIIC_STOP);
    if (recv != len) {
        return XST_FAILURE;
    }

    return XST_SUCCESS;
}

static int sfp_i2c_write_u8(uint8_t dev_addr, uint8_t offset, uint8_t value)
{
    uint8_t buf[2];
    int sent;

    buf[0] = offset;
    buf[1] = value;

    sent = XIic_Send(Iic.BaseAddress, dev_addr, buf, 2, XIIC_STOP);
    return (sent == 2) ? XST_SUCCESS : XST_FAILURE;
}

static int sfp_i2c_read_u8(uint8_t dev_addr, uint8_t offset, uint8_t *value)
{
    return sfp_i2c_random_read(dev_addr, offset, value, 1);
}

static int sfp_i2c_write_u16_be(uint8_t dev_addr, uint8_t offset_msb, uint16_t value)
{
    if (sfp_i2c_write_u8(dev_addr, offset_msb, (uint8_t)((value >> 8) & 0xFF)) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    if (sfp_i2c_write_u8(dev_addr, (uint8_t)(offset_msb + 1), (uint8_t)(value & 0xFF)) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    return XST_SUCCESS;
}

static int sfp_i2c_read_u16_be(uint8_t dev_addr, uint8_t offset_msb, uint16_t *value)
{
    uint8_t buf[2];

    if (sfp_i2c_random_read(dev_addr, offset_msb, buf, 2) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    *value = be16_to_u16(buf);
    return XST_SUCCESS;
}

static int sfp_probe(uint8_t dev_addr)
{
    uint8_t off = 0x00;
    int sent = XIic_Send(Iic.BaseAddress, dev_addr, &off, 1, XIIC_STOP);
    return (sent == 1) ? XST_SUCCESS : XST_FAILURE;
}

static int sfp_8690_select_page(uint8_t page)
{
    if (sfp_i2c_write_u8(SFP_A2_ADDR, SFP_A2_PAGE_SELECT, page) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    usleep(20000);
    return XST_SUCCESS;
}

static int sfp_read_basic_id(void)
{
    uint8_t buf[96];

    if (sfp_i2c_random_read(SFP_A0_ADDR, 0x00, buf, sizeof(buf)) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    copy_ascii_trim_json_safe(g_vendor, &buf[20], 16);
    copy_ascii_trim_json_safe(g_part_number, &buf[40], 16);
    copy_ascii_trim_json_safe(g_serial_number, &buf[68], 16);
    return XST_SUCCESS;
}

static int sfp_8690_read_capability(uint8_t *cap)
{
    if (sfp_8690_select_page(SFP_8690_PAGE_TUNE) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    return sfp_i2c_read_u8(SFP_A2_ADDR, SFP_8690_CAPABILITY, cap);
}

static int sfp_8690_get_channel(uint16_t *ch)
{
    if (sfp_8690_select_page(SFP_8690_PAGE_TUNE) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    return sfp_i2c_read_u16_be(SFP_A2_ADDR, SFP_8690_CHANNEL_MSB, ch);
}

static int sfp_8690_get_status(uint8_t *status, uint8_t *latch_status)
{
    if (sfp_8690_select_page(SFP_8690_PAGE_TUNE) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    if (sfp_i2c_read_u8(SFP_A2_ADDR, SFP_8690_STATUS, status) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    return sfp_i2c_read_u8(SFP_A2_ADDR, SFP_8690_LATCH_STATUS, latch_status);
}

static int sfp_8690_poll_tuning_status(uint8_t *last_status, uint8_t *last_latch)
{
    int retry;

    for (retry = 0; retry < 25; ++retry) {
        if (sfp_8690_get_status(last_status, last_latch) != XST_SUCCESS) {
            return XST_FAILURE;
        }

        if ((*last_status & 0x10U) == 0) {
            break;
        }

        usleep(100000);
    }

    if (*last_latch & 0x10U) {
        return XST_FAILURE;
    }

    return XST_SUCCESS;
}

static int sfp_8690_set_channel(uint16_t ch, uint8_t *status, uint8_t *latch)
{
    uint8_t cap = 0;

    if (ch < 1 || ch > 96) {
        return XST_FAILURE;
    }

    if (sfp_8690_read_capability(&cap) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    g_capability = cap;
    if ((cap & 0x02U) == 0) {
        return XST_FAILURE;
    }

    sfp_set_tx_disable(1);
    usleep(100000);

    if (sfp_8690_select_page(SFP_8690_PAGE_TUNE) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    if (sfp_i2c_write_u16_be(SFP_A2_ADDR, SFP_8690_CHANNEL_MSB, ch) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    usleep(300000);
    if (sfp_8690_poll_tuning_status(status, latch) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    sfp_set_tx_disable(0);
    return XST_SUCCESS;
}

static int sfp_read_ddm_raw(int16_t *temp_raw, uint16_t *vcc_raw, uint16_t *bias_raw,
                            uint16_t *txp_raw, uint16_t *rxp_raw)
{
    uint8_t buf[10];

    if (sfp_i2c_random_read(SFP_A2_ADDR, 0x00, buf, sizeof(buf)) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    *temp_raw = be16_to_s16(&buf[0]);
    *vcc_raw = be16_to_u16(&buf[2]);
    *bias_raw = be16_to_u16(&buf[4]);
    *txp_raw = be16_to_u16(&buf[6]);
    *rxp_raw = be16_to_u16(&buf[8]);
    return XST_SUCCESS;
}

static int sfp_hw_init(void)
{
    g_hw_ready = 0;
    g_vendor[0] = '\0';
    g_part_number[0] = '\0';
    g_serial_number[0] = '\0';
    g_capability = 0;

    if (sfp_gpio_init() != XST_SUCCESS) {
        return XST_FAILURE;
    }

    if (sfp_iic_init() != XST_SUCCESS) {
        return XST_FAILURE;
    }

    sleep(1);

    if (sfp_probe(SFP_A0_ADDR) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    if (sfp_read_basic_id() != XST_SUCCESS) {
        return XST_FAILURE;
    }

    if (sfp_8690_read_capability(&g_capability) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    g_hw_ready = 1;
    return XST_SUCCESS;
}

static int read_command_line(char *buf, int max_len)
{
    int n = 0;

    while (1) {
        char c = inbyte();

        if (c == '\r' || c == '\n') {
            if (n == 0) {
                continue;
            }
            buf[n] = '\0';
            return n;
        }

        if (n < max_len - 1) {
            buf[n++] = c;
        }
    }
}

static void respond_error(const char *error)
{
    xil_printf("{\"ok\":false,\"error\":\"%s\"}\r\n", error);
}

static void handle_info(void)
{
    xil_printf("{\"ok\":true,\"vendor\":\"%s\",\"pn\":\"%s\",\"sn\":\"%s\","
               "\"capability\":%u,\"channel_tuning\":%u,\"wavelength_tuning\":%u}\r\n",
               g_vendor,
               g_part_number,
               g_serial_number,
               (unsigned)g_capability,
               (unsigned)((g_capability & 0x02U) ? 1U : 0U),
               (unsigned)((g_capability & 0x01U) ? 1U : 0U));
}

static void handle_get_channel(void)
{
    uint16_t ch = 0;

    if (sfp_8690_get_channel(&ch) != XST_SUCCESS) {
        respond_error("read channel failed");
        return;
    }

    xil_printf("{\"ok\":true,\"channel\":%u}\r\n", (unsigned)ch);
}

static void handle_set_channel(const char *cmd)
{
    uint16_t ch;
    uint8_t status = 0;
    uint8_t latch = 0;

    ch = (uint16_t)atoi(cmd + strlen("SET_CH"));

    if (ch < 1 || ch > 96) {
        respond_error("channel out of range");
        return;
    }

    if (sfp_8690_set_channel(ch, &status, &latch) != XST_SUCCESS) {
        if ((g_capability & 0x02U) == 0) {
            respond_error("module does not support channel tuning");
        } else if (latch & 0x10U) {
            respond_error("bad channel");
        } else {
            respond_error("set channel failed");
        }
        return;
    }

    xil_printf("{\"ok\":true,\"channel\":%u,\"status\":%u,\"latch_status\":%u,"
               "\"new_channel_acquired\":%u}\r\n",
               (unsigned)ch,
               (unsigned)status,
               (unsigned)latch,
               (unsigned)((latch & 0x08U) ? 1U : 0U));
}

static void handle_get_status(void)
{
    uint8_t status = 0;
    uint8_t latch = 0;

    if (sfp_8690_get_status(&status, &latch) != XST_SUCCESS) {
        respond_error("read status failed");
        return;
    }

    xil_printf("{\"ok\":true,\"status\":%u,\"latch_status\":%u,"
               "\"tx_tune_in_progress\":%u,\"bad_channel\":%u,"
               "\"new_channel_acquired\":%u}\r\n",
               (unsigned)status,
               (unsigned)latch,
               (unsigned)((status & 0x10U) ? 1U : 0U),
               (unsigned)((latch & 0x10U) ? 1U : 0U),
               (unsigned)((latch & 0x08U) ? 1U : 0U));
}

static void handle_get_ddm(void)
{
    int16_t temp_raw;
    uint16_t vcc_raw;
    uint16_t bias_raw;
    uint16_t txp_raw;
    uint16_t rxp_raw;
    int temp_c_x100;

    if (sfp_read_ddm_raw(&temp_raw, &vcc_raw, &bias_raw, &txp_raw, &rxp_raw) != XST_SUCCESS) {
        respond_error("read ddm failed");
        return;
    }

    temp_c_x100 = ((int)temp_raw * 100) / 256;

    xil_printf("{\"ok\":true,\"temperature_c_x100\":%d,\"vcc_mv\":%u,"
               "\"tx_bias_ua\":%u,\"tx_power_uw\":%u,\"rx_power_uw\":%u,"
               "\"raw_temp\":%d,\"raw_vcc\":%u,\"raw_bias\":%u,"
               "\"raw_tx_power\":%u,\"raw_rx_power\":%u}\r\n",
               temp_c_x100,
               (unsigned)(vcc_raw / 10U),
               (unsigned)(bias_raw * 2U),
               (unsigned)(txp_raw / 10U),
               (unsigned)(rxp_raw / 10U),
               (int)temp_raw,
               (unsigned)vcc_raw,
               (unsigned)bias_raw,
               (unsigned)txp_raw,
               (unsigned)rxp_raw);
}

static void handle_tx(const char *cmd)
{
    if (strcmp(cmd, "TX ON") == 0) {
        sfp_set_tx_disable(0);
        xil_printf("{\"ok\":true,\"tx_disabled\":0}\r\n");
    } else if (strcmp(cmd, "TX OFF") == 0) {
        sfp_set_tx_disable(1);
        xil_printf("{\"ok\":true,\"tx_disabled\":1}\r\n");
    } else {
        respond_error("use TX ON or TX OFF");
    }
}

static void handle_help(void)
{
    xil_printf("{\"ok\":true,\"commands\":[\"INFO\",\"GET_CH\",\"SET_CH <1..96>\","
               "\"GET_STATUS\",\"GET_DDM\",\"TX ON\",\"TX OFF\",\"HELP\"]}\r\n");
}

static void handle_command(char *cmd)
{
    if (!g_hw_ready && strcmp(cmd, "HELP") != 0) {
        respond_error("hardware init failed");
        return;
    }

    if (strcmp(cmd, "INFO") == 0) {
        handle_info();
    } else if (strcmp(cmd, "GET_CH") == 0) {
        handle_get_channel();
    } else if (starts_with(cmd, "SET_CH")) {
        handle_set_channel(cmd);
    } else if (strcmp(cmd, "GET_STATUS") == 0) {
        handle_get_status();
    } else if (strcmp(cmd, "GET_DDM") == 0) {
        handle_get_ddm();
    } else if (starts_with(cmd, "TX")) {
        handle_tx(cmd);
    } else if (strcmp(cmd, "HELP") == 0) {
        handle_help();
    } else {
        respond_error("unknown command");
    }
}

int main(void)
{
    char cmd[CMD_MAX_LEN];

    (void)sfp_hw_init();

    while (1) {
        read_command_line(cmd, sizeof(cmd));
        handle_command(cmd);
    }

    return 0;
}
