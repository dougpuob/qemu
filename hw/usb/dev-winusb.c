/*
 * USB WinUsb Device emulation
 *
 * Copyright (c) 2022 Genesys Logic.
 * Written by Douglas Chen <Douglas.Chen@genesyslogic.com.tw>
 *
 * This code is licensed under the LGPL.
 */

#include "qemu/osdep.h"
#include "hw/usb.h"
#include "desc.h"
#include "desc-msos.h"
#include "migration/vmstate.h"
#include "qom/object.h"
#include "trace.h"

typedef struct _DataBuffer {
    uint8_t* data;
    int len;;
} DataBuffer;

typedef struct _LoopDevices {
    DataBuffer bulk;
} LoopDevices;

struct WinUsbState {
    USBDevice dev;

    /* Buffer of Loop devices */
    LoopDevices loop_devs;

    USBPacket *packet;
    /* WinUSB only. */
};

typedef struct WinUsbState WinUsbState;
#define TYPE_USB_WINUSB "usb-winusb"
DECLARE_INSTANCE_CHECKER(WinUsbState, USB_WINUSB_DEV,
                         TYPE_USB_WINUSB)

enum {
    STR_MANUFACTURER = 1,
    STR_PRODUCT,
    STR_SERIALNUMBER,
    STR_CONFIG_FULL,
    STR_CONFIG_HIGH
};

static const USBDescStrings desc_strings = {
    [STR_MANUFACTURER] = "GenesysLogic",
    [STR_PRODUCT]      = "QEMU WinUsb Device",
    [STR_SERIALNUMBER] = "000000000012",
    [STR_CONFIG_FULL]  = "Full speed config (USB 1.1)",
    [STR_CONFIG_HIGH]  = "High speed config (USB 2.0)",
};

static const USBDescIface desc_iface_full = {
        .bInterfaceNumber              = 0,
        .bNumEndpoints                 = 2,
        .bInterfaceClass               = USB_CLASS_VENDOR_SPEC,
        .bInterfaceSubClass            = 0x06, /* SCSI */
        .bInterfaceProtocol            = 0x50, /* Bulk */
        .eps = (USBDescEndpoint[]) {
            {
                .bEndpointAddress      = USB_DIR_IN | 0x01,
                .bmAttributes          = USB_ENDPOINT_XFER_BULK,
                .wMaxPacketSize        = 64,
            },{
                .bEndpointAddress      = USB_DIR_OUT | 0x02,
                .bmAttributes          = USB_ENDPOINT_XFER_BULK,
                .wMaxPacketSize        = 64,
            },
            // {
            //     .bEndpointAddress      = USB_DIR_IN | 0x03,
            //     .bmAttributes          = USB_ENDPOINT_XFER_INT,
            //     .wMaxPacketSize        = 9,
            //     .bInterval             = 2,
            // },
            // {
            //     .bEndpointAddress      = USB_DIR_OUT | 0x04,
            //     .bmAttributes          = USB_ENDPOINT_XFER_INT,
            //     .wMaxPacketSize        = 9,
            //     .bInterval             = 2,
            // },
        }
    //}
    // ,
    // {
    //     .bInterfaceNumber              = 1,
    //     .bNumEndpoints                 = 2,
    //     .bInterfaceClass               = USB_CLASS_VENDOR_SPEC,
    //     .bInterfaceSubClass            = 0x00, /*(No Subclass)*/
    //     .bInterfaceProtocol            = 0x00, /*(None)*/
    //     .eps = (USBDescEndpoint[]) {
    //         {
    //             .bEndpointAddress      = USB_DIR_IN | 0x03,
    //             .bmAttributes          = USB_ENDPOINT_XFER_INT,
    //             .wMaxPacketSize        = 9,
    //             .bInterval             = 2,
    //         },
    //         {
    //             .bEndpointAddress      = USB_DIR_OUT | 0x04,
    //             .bmAttributes          = USB_ENDPOINT_XFER_INT,
    //             .wMaxPacketSize        = 9,
    //             .bInterval             = 2,
    //         },
    //     }
    // }
};

static const USBDescDevice desc_device_full = {
    .bcdUSB                        = 0x0200,
    .bMaxPacketSize0               = 8,
    .bNumConfigurations            = 1,
    .confs = (USBDescConfig[]) {
        {
            .bNumInterfaces        = 1,
            .bConfigurationValue   = 1,
            .iConfiguration        = STR_CONFIG_FULL,
            .bmAttributes          = USB_CFG_ATT_ONE | USB_CFG_ATT_SELFPOWER,
            .nif = 1,
            .ifs = &desc_iface_full,
        },
    },
};

static const USBDescIface desc_iface_high = {
    .bInterfaceNumber              = 0,
    .bNumEndpoints                 = 2,
    .bInterfaceClass               = USB_CLASS_VENDOR_SPEC,
    .bInterfaceSubClass            = 0x06, /* SCSI */
    .bInterfaceProtocol            = 0x50, /* Bulk */
    .eps = (USBDescEndpoint[]) {
        {
            .bEndpointAddress      = USB_DIR_IN | 0x01,
            .bmAttributes          = USB_ENDPOINT_XFER_BULK,
            .wMaxPacketSize        = 512,
        },{
            .bEndpointAddress      = USB_DIR_OUT | 0x02,
            .bmAttributes          = USB_ENDPOINT_XFER_BULK,
            .wMaxPacketSize        = 512,
        },
    }
};

static const USBDescDevice desc_device_high = {
    .bcdUSB                        = 0x0200,
    .bMaxPacketSize0               = 9,
    .bNumConfigurations            = 1,
    .confs = (USBDescConfig[]) {
        {
            .bNumInterfaces        = 1,
            .bConfigurationValue   = 1,
            .iConfiguration        = STR_CONFIG_HIGH,
            .bmAttributes          = USB_CFG_ATT_ONE | USB_CFG_ATT_SELFPOWER,
            .nif = 1,
            .ifs = &desc_iface_high,
        },
    },
};

static const USBDescMSOS desc_msos = {
    .bMS_VendorCode       = MSOS_VENDOR_CODE_QEMU,
    .CompatibleID         = "WINUSB",
    .RegistryPropertyName = L"DeviceInterfaceGUID",
    .RegistryPropertyData = L"{85239cd7-da0f-44ea-a9c8-da8cc28f8564}",
};

static const USBDesc desc = {
    .id = {
        .idVendor          = 0x05E3,
        .idProduct         = 0x3E50,
        .bcdDevice         = 0x0000,
        .iManufacturer     = STR_MANUFACTURER,
        .iProduct          = STR_PRODUCT,
        .iSerialNumber     = STR_SERIALNUMBER,
    },
    .full  = &desc_device_full,
    .high  = &desc_device_high,
    .str   = desc_strings,
    .msos  = &desc_msos,
};

static void usb_winusb_initfn(USBDevice *dev, const USBDesc *desc,
                           Error **errp)
{
    dev->usb_desc = desc;
    usb_desc_init(dev);
}

static void usb_winusb_realize(USBDevice *dev, Error **errp)
{
    WinUsbState *s = USB_WINUSB_DEV(dev);
    if (s) {
        s->loop_devs.bulk.len = 200;
        s->loop_devs.bulk.data = g_malloc0(s->loop_devs.bulk.len);
    }
    usb_winusb_initfn(dev, &desc, errp);
}

static void usb_winusb_unrealize(USBDevice *dev)
{
    WinUsbState *s = USB_WINUSB_DEV(dev);
    if (s->loop_devs.bulk.data) {
        g_free(s->loop_devs.bulk.data);
        s->loop_devs.bulk.data = NULL;
    }
}

// static void usb_winusb_packet_complete(USBDevice *dev, USBPacket *p)
// {
//     p->state = USB_PACKET_ASYNC;
//     usb_packet_complete(dev, p);
// }

static void usb_winusb_handle_reset(USBDevice *dev)
{
    trace_usb_winusb_handle_reset(dev);
    WinUsbState *s = USB_WINUSB_DEV(dev);
    if (s->loop_devs.bulk.data) {
        memset(s->loop_devs.bulk.data, 0, s->loop_devs.bulk.len);
    }
}

static void usb_winusb_handle_control(USBDevice *dev, USBPacket *p,
               int request, int value, int index, int length, uint8_t *data)
{
    int ret = 0;
    WinUsbState *s = USB_WINUSB_DEV(dev);

    trace_usb_winusb_handle_control(dev, request, value, index, length);

    ret = usb_desc_handle_control(dev, p, request, value, index, length, data);
    if (ret >= 0) {
        return;
    }

    switch (request) {
    case EndpointOutRequest | USB_REQ_CLEAR_FEATURE:
        switch (index) {
        case 0x02:
        case 0x81:
            if (s->loop_devs.bulk.data) {
                memset(s->loop_devs.bulk.data, 0, s->loop_devs.bulk.len);
            }
            break;
        default:
            break;
        }
        break;
    default:
        p->status = USB_RET_STALL;
        break;
    }

    return;
}

static void usb_winusb_cancel_io(USBDevice *dev, USBPacket *p)
{
    WinUsbState *s = USB_WINUSB_DEV(dev);
    trace_usb_winusb_cancel_io(dev);

    assert(s->packet == p);
    s->packet = NULL;
}

static void usb_winusb_handle_data(USBDevice *dev, USBPacket *p)
{
    WinUsbState *s = USB_WINUSB_DEV(dev);

    trace_usb_winusb_handle_data(dev);

    switch (p->pid) {
    case USB_TOKEN_OUT:
        // Write Pipe
        if (s->loop_devs.bulk.data) {
            int copy_size = s->loop_devs.bulk.len;
            copy_size = MIN(copy_size, p->iov.size);
            usb_packet_copy(p, s->loop_devs.bulk.data, copy_size);
        }
        break;
    case USB_TOKEN_IN:
        // Read Pipe
        if (s->loop_devs.bulk.data) {
            int copy_size = s->loop_devs.bulk.len;
            copy_size = MIN(copy_size, p->iov.size);
            usb_packet_copy(p, s->loop_devs.bulk.data, copy_size);
        }
        break;
    default:
        p->status = USB_RET_STALL;
        break;
    }
}

static const VMStateDescription vmstate_winusb = {
    .name = "usb-winusb",
    .version_id = 1,
    .minimum_version_id = 1,
};

static void usb_winusb_class_initfn_common(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    USBDeviceClass *uc = USB_DEVICE_CLASS(klass);

    uc->product_desc   = "QEMU USB WinUSB";
    uc->usb_desc       = &desc;
    uc->cancel_packet  = usb_winusb_cancel_io;
    uc->handle_reset   = usb_winusb_handle_reset;
    uc->handle_control = usb_winusb_handle_control;
    uc->handle_data    = usb_winusb_handle_data;
    set_bit(DEVICE_CATEGORY_USB, dc->categories);

    dc->fw_name = "winusb";
    dc->vmsd = &vmstate_winusb;

    uc->realize = usb_winusb_realize;
    uc->unrealize = usb_winusb_unrealize;
}

static const TypeInfo usb_winusb_dev_type_info = {
    .name          = TYPE_USB_WINUSB,
    .parent        = TYPE_USB_DEVICE,
    .instance_size = sizeof(WinUsbState),
    .class_init    = usb_winusb_class_initfn_common,
};

static void usb_winusb_register_types(void)
{
    type_register_static(&usb_winusb_dev_type_info);
}

type_init(usb_winusb_register_types)
