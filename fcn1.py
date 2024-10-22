# -*- coding: utf-8 -*-
"""FCN1.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1LfCPhf72lSufnM0OOGJPL8YtA7A-ZYr-
"""

import os
import cv2
import numpy as np
import xml.etree.ElementTree as ET
from google.colab.patches import cv2_imshow

from google.colab import drive
drive.mount('/content/drive')

class XMLParser:
    """A XML parser for loading annotated CT image.
    """
    def __init__(self, xml_path: str, labels: list[str], thickness=1):
        """Initialize a XML parser.

        Args:
            xml_path: path to .xml file.
            labels: labels for parsing.
            thickness: polyline thickness in drawing.
        """

        ## create annotation label map (label->idx)
        self.labels = {label: idx for idx, label in enumerate(sorted(labels))}

        ## parse the .xml file to a tree
        tree = ET.parse(xml_path)
        root = tree.getroot()

        ## select the images from root
        self.images = [child for child in root if child.tag == "image"]
        self.images = sorted(self.images, key=lambda x: int(x.attrib['id']))

        ## polyline thickness
        self.thickness = thickness

    def __len__(self)->int:
        """Size of the annotated images.
        """
        return len(self.images)

    def __getitem__(self, idx: int)->dict:
        """Annotation of the idx image.
        """
        return self._parse_image_annotation(self.images[idx])

    def _parse_image_annotation(self, root: ET.Element)->dict:
        """Parse the polygons/polylines information based on its annotation.

        Args:
            root: an image root in the tree.

        Return:
            annotation: annotation dictionary of the image.
        """
        annotation = root.attrib.copy()

        ## parse the annotation and save to the dict
        annotation['records'] = []

        ## initialize segmentation mask
        H = int(annotation["height"])
        W = int(annotation["width"])
        canvas = np.zeros((H, W, len(self.labels)), dtype=np.uint8)

        for child in root:
            label = child.attrib['label']

            if label not in self.labels:
                continue

            record = {}

            if child.tag == "polygon" or child.tag == "polyline":
                record["type"]   = child.tag
                record["label"]  = self.labels[label]
                record["points"] = child.attrib["points"]

                annotation['records'].append(record)

                points = self._parse_points(child.attrib['points'])

                ## draw polygon/polyline on individual channel
                label_idx = self.labels[label]
                if child.tag == "polygon":
                    _canvas = canvas[:,:,label_idx].copy()
                    canvas[:,:,label_idx] = self._draw_polygon(_canvas, points)
                else:
                    _canvas = canvas[:,:,label_idx].copy()
                    canvas[:,:,label_idx] = self._draw_polyline(_canvas, points)

        annotation["mask"] = canvas

        return annotation

    def _draw_polygon(self, canvas, points):
        """
        A helper function to draw the polygon on canvas.
        """

        canvas = cv2.fillPoly(canvas, [points], 1)

        return canvas

    def _draw_polyline(self, canvas, points):
        """
        A helper function to draw the polyline on canvas.
        """

        canvas = cv2.polylines(canvas, [points], False, 1, thickness=self.thickness)

        return canvas

    def _parse_points(self, points):
        """
        A helper function to parse points from .xml file.
        """

        points = points.split(";")

        pts = []

        for point in points:
            x, y = point.split(",")
            x, y = eval(x), eval(y)

            pts.append((x, y))

        pts = np.array(pts).reshape((-1, 1, 2)).astype(int)

        return pts

CT_LABEL = ["crack", "pore"]
XML_PATH =  '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/SA_annotations.xml'    ## change xml_path as needed

parser = XMLParser(XML_PATH, CT_LABEL)
print(f"{XML_PATH} has {len(parser)} annotated images.")

idx = 10
annotation = parser[idx]
segmentation_mask = annotation["mask"]

channel = parser.labels["crack"]
cv2_imshow(segmentation_mask[:,:,channel] * 255)

channel = parser.labels["pore"]
cv2_imshow(segmentation_mask[:,:,channel] * 255)

import torch
from torch.utils.data import Dataset
from torchvision.io import read_image
import torchvision.transforms as transforms

class CTImageDataset(Dataset):
    def __init__(self, img_roots, xml_paths, labels=[], thickness=2, transform=None):
        self.img_roots = img_roots
        self.parsers = [XMLParser(path, labels, thickness) for path in xml_paths]
        self.prefix_sum = [0] + [sum(len(parser) for parser in self.parsers[:i + 1]) for i in range(len(self.parsers))]
        self.transform = transform

    def __len__(self):
        return self.prefix_sum[-1]

    def __getitem__(self, idx):
        if idx >= len(self):
            raise IndexError
        while idx < 0:
            idx += len(self)
        parser_idx = self._idxSearch(idx)
        parser = self.parsers[parser_idx]
        annotation_idx = idx - self.prefix_sum[parser_idx]
        annotation = parser[annotation_idx]
        image_path = self._find_image(annotation["name"])
        if image_path is None:
            raise FileNotFoundError(f"Image {annotation['name']} not found in any of the provided roots.")
        image = cv2.imread(image_path, 0)
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        seg_mask = annotation['mask']
        image = self._toTensor(image)
        seg_mask = self._toTensor(seg_mask)
        if self.transform:
            merged = torch.cat([image, seg_mask], dim=0)
            merged = self.transform(merged)
            image, seg_mask = merged[:3, :, :], merged[3:, :, :]
        return image, seg_mask

    def _idxSearch(self, target):
        for i in range(len(self.parsers)):
            if self.prefix_sum[i] <= target < self.prefix_sum[i + 1]:
                return i
        return len(self.parsers) - 1

    def _find_image(self, image_name):
        for root in self.img_roots:
            image_path = os.path.join(root, image_name)
            if os.path.exists(image_path):
                return image_path
        return None

    def _toTensor(self, img):
        if len(img.shape) == 2:
            img = img[:, :, np.newaxis]
        tensor = torch.from_numpy(img).permute([2, 0, 1]).float()
        return tensor

    @property
    def labels(self):
        return self.parsers[0].labels

from google.colab import drive
drive.mount('/content/drive')

IMG_ROOT = ['/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata1',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata2',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata3',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata4',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata5',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata6',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata7',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata8',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata9',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata10',
                      '/content/drive/My Drive/Amber Lab/CT DATA/Open Data/ctdata11'
]

XML_ROOT = "/content/drive/My Drive/Amber Lab/CT DATA/Open Data/annotations"

xml_paths = os.listdir(XML_ROOT)
xml_paths = [os.path.join(XML_ROOT, path) for path in xml_paths if ".xml" in path]

transform_list = [transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(), transforms.RandomCrop([1024, 1024])]
transform = transforms.Compose(transform_list)

dataset = CTImageDataset(IMG_ROOT, xml_paths, labels=["crack", "pore"], transform=transform)
print(f"CTImageDataset has {len(dataset)} images in total.")
print(dataset.labels)

idx = 2

X, y = dataset[idx]

cv2_imshow(X.numpy().transpose(1, 2, 0))

cv2_imshow(y[1, :, :].numpy() * 255)

from torch.utils.data import Dataset, DataLoader, random_split

transform_list = [transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(), transforms.RandomCrop([1024, 1024])]
transform = transforms.Compose(transform_list)

dataset = CTImageDataset(IMG_ROOT, xml_paths, labels=["crack", "pore"], transform=transform)
print(f"CTImageDataset has {len(dataset)} images in total.")
print(dataset.labels)

train_ratio = 0.8
train_size = int(train_ratio * len(dataset))
val_size = len(dataset) - train_size

train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True, num_workers=0, pin_memory=True)
val_loader = DataLoader(val_dataset, batch_size=1, shuffle=False, num_workers=0, pin_memory=True)

# Define FCN Model

train_dataset = CTImageDataset(IMG_ROOT, xml_paths, labels=["crack", "pore"], thickness=2, transform=transform)
val_dataset   = CTImageDataset(IMG_ROOT, xml_paths, labels=["crack", "pore"], thickness=2, transform=None)

## split dataset
train_ratio = 0.8
train_size = int(train_ratio * len(train_dataset))
val_size = len(train_dataset) - train_size

train_dataset, _ = random_split(train_dataset, [train_size, val_size])
_, val_dataset = random_split(val_dataset, [train_size, val_size])

## wrap to dataloader
train_loader = DataLoader(train_dataset, batch_size=3, shuffle=True, num_workers=0, pin_memory=True)
val_loader   = DataLoader(val_dataset, batch_size=1, shuffle=False, num_workers=0, pin_memory=True)

for X, y in train_loader:
    print(X.shape, y.shape)

import torch
import torch.nn as nn
import torch.nn.functional as F

import os
import cv2
import numpy as np
import xml.etree.ElementTree as ET
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
from torchvision import transforms, models
from google.colab import drive
from google.colab.patches import cv2_imshow



class FCN(nn.Module):
    def __init__(self, num_classes):
        super(FCN, self).__init__()
        self.backbone = models.resnet50(pretrained=True)
        self.backbone = nn.Sequential(*list(self.backbone.children())[:-2])
        self.conv = nn.Conv2d(2048, num_classes, kernel_size=1)

    def forward(self, x):
        x = self.backbone(x)
        x = self.conv(x)
        x = nn.functional.interpolate(x, size=(x.shape[2]*32, x.shape[3]*32), mode='bilinear', align_corners=False)
        return x

# DataLoader setup (reduce batch size if necessary)
train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True, num_workers=0, pin_memory=True)
val_loader = DataLoader(val_dataset, batch_size=1, shuffle=False, num_workers=0, pin_memory=True)

class FCN(nn.Module):
    def __init__(self, num_classes):
        super(FCN, self).__init__()
        self.conv1 = nn.Conv2d(3, 64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(128, 256, kernel_size=3, padding=1)
        self.conv4 = nn.Conv2d(256, 512, kernel_size=3, padding=1)

        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

        self.deconv4 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        self.deconv3 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.deconv2 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.deconv1 = nn.ConvTranspose2d(64, num_classes, kernel_size=2, stride=2)

    def forward(self, x):
        x1 = self.pool(F.relu(self.conv1(x)))  # [N, 64, H/2, W/2]
        x2 = self.pool(F.relu(self.conv2(x1)))  # [N, 128, H/4, W/4]
        x3 = self.pool(F.relu(self.conv3(x2)))  # [N, 256, H/8, W/8]
        x4 = self.pool(F.relu(self.conv4(x3)))  # [N, 512, H/16, W/16]

        x = F.relu(self.deconv4(x4))  # [N, 256, H/8, W/8]
        x = x + x3  # Add skip connection from x3
        x = F.relu(self.deconv3(x))  # [N, 128, H/4, W/4]
        x = x + x2  # Add skip connection from x2
        x = F.relu(self.deconv2(x))  # [N, 64, H/2, W/2]
        x = x + x1  # Add skip connection from x1
        x = self.deconv1(x)  # [N, num_classes, H, W]

        return x

num_classes = len(["crack", "pore"])
fcn = FCN(num_classes)

criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(fcn.parameters(), lr=1e-4)

def train(model, train_loader, criterion, optimizer, num_epochs=25):
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0
        for images, targets in train_loader:
            #images = images.cuda()
            #targets = targets.cuda()
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * images.size(0)
        train_loss /= len(train_loader.dataset)
        print(f'Epoch {epoch+1}/{num_epochs}, Training Loss: {train_loss:.4f}')

def validate(model, val_loader, criterion):
    model.eval()
    val_loss = 0
    with torch.no_grad():
        for images, targets in val_loader:
            #images = images.cuda()
            #targets = targets.cuda()
            outputs = model(images)
            loss = criterion(outputs, targets)
            val_loss += loss.item() * images.size(0)
    val_loss /= len(val_loader.dataset)
    return val_loss

# Train and validate the model
num_epochs = 2
train(fcn, train_loader, criterion, optimizer, num_epochs)
val_loss = validate(fcn, val_loader, criterion)
print(f'Validation Loss: {val_loss:.4f}')