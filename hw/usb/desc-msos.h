#ifndef QEMU_HW_USB_DESC_MSOS_H
#define QEMU_HW_USB_DESC_MSOS_H

/* Microsoft OS 1.0 Descriptors Specification (OS_Desc_Intro.doc)
 * (https://download.microsoft.com/download/9/C/5/9C5B2167-8017-4BAE-9FDE-D599BAC8184A/OS_Desc_Ext_Prop.zip)
 */
#define MSOS_DESC_INDEX (0xee)

/* generate microsoft string descriptor from structs */
int usb_desc_msos_str_desc(const char* str, uint8_t *dest, uint8_t ven_code);

#endif /* QEMU_HW_USB_DESC_MSOS_H */
